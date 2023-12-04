import discord,asyncio,random,datetime

from core.classes import Cog_Extension
from discord.ext import commands
from discord.commands import SlashCommandGroup
from starcord import BotEmbed,sclient,ChoiceList
from starcord.FileDatabase import Jsondb
from starcord.types.rpg import ItemCategory
from starcord.ui_element.RPGview import RPGAdvanceView
from starcord.models import GameInfoPage,RPGItem,ShopItem
from starcord.types import Coins,ItemCategory,ShopItemMode

rpgcareer_option = ChoiceList.set("rpgcareer_option")

class role_playing_game(Cog_Extension):
    work = SlashCommandGroup("work", "工作相關指令")
    rpgshop = SlashCommandGroup("rpgshop", "rpg商店相關指令")
    
    @commands.slash_command(description='進行冒險（開發中）')
    async def advance(self,ctx:discord.ApplicationContext):
        # await ctx.respond('敬請期待',ephemeral=False)
        # return
        await ctx.respond(view=RPGAdvanceView(ctx.author.id))

    @work.command(description='進行工作（開發中）')
    async def start(self,ctx:discord.ApplicationContext):
        # dbdata = sclient.get_activities(ctx.author.id)
        # if dbdata.get("work_date") == datetime.date.today():
        #     await ctx.respond("今天已經工作過了")
        
        # await ctx.respond(view=RPGbutton2(ctx.author.id))
        rpguser = sclient.get_rpguser(ctx.author.id)
        if not rpguser.career_id:
            await ctx.respond(embed=BotEmbed.rpg("工作結果",f"你現在是無業游民，請選擇職業再工作"))
            return
        
        now = datetime.datetime.now()
        dbdata = sclient.get_work(rpguser.discord_id)
        last_work = dbdata.get("last_work")
        if last_work and now - last_work < datetime.timedelta(hours=11):
            next_work = int((last_work + datetime.timedelta(hours=11)).timestamp())
            embed = BotEmbed.rpg("工作結果",f"你已經工作過了，請等到 <t:{next_work}> 再繼續工作")
        else:
            next_work = int((now + datetime.timedelta(hours=11)).timestamp())
            reward_item_uid = dbdata.get("reward_item_uid")
            reward_item_name = dbdata.get("item_name")
            reward_item_min = dbdata.get("reward_item_min",0)
            reward_item_max = dbdata.get("reward_item_max",0)
            
            if reward_item_uid:
                reward_item_get = random.randint(reward_item_min,reward_item_max)
                hard_woring_rate = (reward_item_get - reward_item_min) / (reward_item_max - reward_item_min) if reward_item_max != 0 else 0
                sclient.update_bag(rpguser.discord_id,reward_item_uid,reward_item_get)
                
                if hard_woring_rate == 0:
                    work_text = "你工作時出了點狀況"
                elif hard_woring_rate <= 0.25:
                    work_text = "你隨便做完了工作"
                elif hard_woring_rate > 0.25 and hard_woring_rate <= 0.5:
                    work_text = "你心不在焉的工作"
                elif hard_woring_rate < 0.5 and hard_woring_rate <= 0.75:
                    work_text = "你普普通通的工作"
                elif hard_woring_rate != 1:
                    work_text = "你勤奮的完成工作"
                else:
                    work_text = "你一人承擔所有工作"

                embed = BotEmbed.rpg("工作結果",f"{work_text}，獲得 {reward_item_name} * {reward_item_get}\n下次工作時間：<t:{next_work}>")
            else:
                embed = BotEmbed.rpg("工作結果",f"你勤奮的打工\n下次工作時間：<t:{next_work}>")
            
            sclient.refresh_work(rpguser.discord_id)
        
        await ctx.respond(embed=embed)

    @work.command(description='選擇職業（開發中）')
    async def career(self,ctx:discord.ApplicationContext,
                    career_id:discord.Option(int,name='工作職業',description='',choices=rpgcareer_option,default=None)):
        sclient.set_rpguser_data(ctx.author.id,"career_id",career_id)
        embed = BotEmbed.rpg("工作職業",f"已選擇職業 {ChoiceList.get_tw(career_id,'rpgcareer_option')}" if career_id else "你成為無業遊民了")
        await ctx.respond(embed=embed)

    @commands.slash_command(description='查看用戶資訊')
    async def ui(self,ctx:discord.ApplicationContext,user_dc:discord.Option(discord.Member,name='用戶',description='留空以查詢自己',default=None)):
        user_dc = user_dc or ctx.author
        user = sclient.get_dcuser(user_dc.id,True,user_dc)
        if not user:
            sclient.create_discord_user(user_dc.id)
            user = sclient.get_dcuser(user_dc.id,True,user_dc)

        pet = user.get_pet()
        game = user.get_game()
        pet_embed = pet.desplay(user_dc) if pet else BotEmbed.simple(f'{user_dc.name} 的寵物','用戶沒有認養寵物')
        game_embed = game.desplay(user_dc) if game else GameInfoPage().desplay(user_dc)
        await ctx.respond(embeds=[user.desplay(self.bot), pet_embed, game_embed])

    @commands.slash_command(description='查看RPG資訊')
    async def rpgui(self,ctx:discord.ApplicationContext,user_dc:discord.Option(discord.Member,name='用戶',description='留空以查詢自己',default=None)):
        user_dc = user_dc or ctx.author
        user = sclient.get_rpguser(user_dc.id,full=True,user_dc=user_dc)
        await ctx.respond(embeds=[user.desplay(),user.equipment.desplay(user_dc)])

    @commands.slash_command(description='查看背包（開發中）')
    async def bag(self,ctx:discord.ApplicationContext,user_dc:discord.Option(discord.Member,name='用戶',description='留空以查詢自己',default=None)):
        user_dc = user_dc or ctx.author
        dbdata = sclient.get_bag_desplay(user_dc.id)
        embed = BotEmbed.rpg(f'{user_dc.name}的包包')
        if dbdata:
            dict = {}
            for i in Jsondb.jdict.get("rpgitem_category"):
                dict[i] = []
            
            for item_data in dbdata:
                item = RPGItem(item_data)
                dict[str(item.category.value)].append(item)
            
            for i in dict:
                if dict[i]:
                    text = "\n".join([f"{item.name} x{item.amount}" for item in dict[i]])
                    embed.add_field(name=Jsondb.get_jdict("rpgitem_category",i),value=text)
        else:
            embed.description = '背包空無一物'
        await ctx.respond(embed=embed)

    @rpgshop.command(description='查看RPG商店（開發中）')
    async def list(self,ctx):
        dbdata = sclient.get_rpg_shop_list()
        embed = BotEmbed.rpg(title="RPG商城")
        for i in dbdata:
            item = ShopItem(i)
            if item.mode == ShopItemMode.buy:
                mode = "購買"
            else:
                mode = "售出"
            embed.add_field(name=f"[{item.shop_item_id}] {item.name}({mode})",value=f"${item.price}")
        await ctx.respond(embed=embed)

    @rpgshop.command(description='售出物品給RPG商店（開發中）')
    async def sell(self,ctx,
                   shop_item_id:discord.Option(int,name='商品id',description='要售出的商品'),
                   amount:discord.Option(int,name='數量',description='要售出的數量',default=1,min_value=1)):
        item = sclient.get_rpg_shop_item(shop_item_id)
        if not item or item.mode != ShopItemMode.sell:
            await ctx.respond(f"{ctx.author.mention}：商店不買這個喔")
            return
        
        seller_id = sclient.getif_bag(ctx.author.id,item.item_uid,amount)
        if seller_id:
            sclient.update_bag(ctx.author.id,item.item_uid,amount*-1)
            sclient.update_coins(ctx.author.id,"add",Coins.RCOIN,item.price * amount)
            sclient.update_rpg_shop_inventory(item.shop_item_id,amount)
            await ctx.respond(f"{ctx.author.mention}：已售出 {item.name} * {amount}")
        else:
            await ctx.respond(f"{ctx.author.mention}：你的東西數量不夠喔")

    @rpgshop.command(description='購買RPG商店物品（開發中）')
    async def buy(self,ctx,
                  shop_item_id:discord.Option(int,name='商品id',description='要購買的商品'),
                  amount:discord.Option(int,name='數量',description='要售出的數量',default=1,min_value=1)):
        item = sclient.get_rpg_shop_item(shop_item_id)
        if not item or item.mode != ShopItemMode.buy:
            await ctx.respond(f"{ctx.author.mention}：商店沒有賣這個喔")
            return
        
        buyer_id = sclient.getif_coin(ctx.author.id,item.price * amount,Coins.RCOIN)
        if buyer_id:
            sclient.update_bag(ctx.author.id,item.item_uid,amount)
            await ctx.respond(f"{ctx.author.mention}：已購買 {item.name} * {amount}")
        else:
            await ctx.respond(f"{ctx.author.mention}：Rcoin不足")

def setup(bot):
    bot.add_cog(role_playing_game(bot))