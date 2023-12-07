import discord,asyncio,random,datetime

from core.classes import Cog_Extension
from discord.ext import commands,pages
from discord.commands import SlashCommandGroup
from starcord import BotEmbed,sclient,ChoiceList
from starcord.FileDatabase import Jsondb
from starcord.models.user import RPGUser
from starcord.ui_element.RPGview import RPGAdvanceView,RPGEquipmentBagView
from starcord.models import GameInfoPage,RPGItem,ShopItem,RPGEquipment
from starcord.types import Coins,ItemCategory,ShopItemMode,EquipmentSolt

rpgcareer_option = ChoiceList.set("rpgcareer_option")

class role_playing_game(Cog_Extension):
    work = SlashCommandGroup("work", "工作相關指令")
    rpgshop = SlashCommandGroup("rpgshop", "rpg商店相關指令")
    equip = SlashCommandGroup("equip", "裝備相關指令")
    itemcmd = SlashCommandGroup("item", "物品相關指令")
    
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
        await ctx.respond(embeds=[user.desplay(),user.waring_equipment.desplay(user_dc)])

    @itemcmd.command(description='查看背包（開發中）')
    async def bag(self,ctx:discord.ApplicationContext,user_dc:discord.Option(discord.Member,name='用戶',description='留空以查詢自己',default=None)):
        user_dc = user_dc or ctx.author
        rpguser = sclient.get_rpguser(user_dc.id,sclient,user_dc)
        bag = rpguser.itembag
        
        embed = BotEmbed.rpg(f'{user_dc.name}的包包',"")
        embed.description = f"Rcoin：{rpguser.rcoin}"
        if bag:
            dict = {}
            for i in Jsondb.jdict.get("rpgitem_category"):
                dict[i] = []
            
            for item in bag:
                dict[str(item.category.value)].append(item)
            
            for i in dict:
                if dict[i]:
                    text = "\n".join([f"{item.name} x{item.amount}" for item in dict[i]])
                    embed.add_field(name=Jsondb.get_jdict("rpgitem_category",i),value=text)
        else:
            embed.description += '背包空無一物'
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
            sclient.update_coins(ctx.author.id,"add",Coins.RCOIN,item.price * amount * -1)
            await ctx.respond(f"{ctx.author.mention}：已購買 {item.name} * {amount}")
        else:
            await ctx.respond(f"{ctx.author.mention}：Rcoin不足")

    @equip.command(description='查看裝備背包（開發中）')
    async def bag(self,ctx:discord.ApplicationContext,user_dc:discord.Option(discord.Member,name='用戶',description='留空以查詢自己',default=None)):
        await ctx.defer()
        user_dc = user_dc or ctx.author
        dbdata = sclient.get_equipmentbag_desplay(user_dc.id)

        if dbdata:
            # page = []
            # page_count = -1
            # item_count = 9
            
            # for item in dbdata.items:
            #     item:RPGEquipment
            #     if item_count == 9:
            #         page_count += 1
            #         item_count = 0
            #         page.append(BotEmbed.rpg(f'{user_dc.name}的裝備包包'," "))
                
            #     name = f"{item.customized_name}({item.name})" if item.customized_name else item.name
            #     page[page_count].description += f"[{item.equipment_uid}] {name}\n"
            #     item_count += 1

            view = RPGEquipmentBagView(dbdata,ctx.author)
            page = view.refresh_item_page()
            paginator = pages.Paginator(pages=page, use_default_buttons=True,loop_pages=True,custom_view=view)
            view.paginator = paginator
            await paginator.respond(ctx.interaction, ephemeral=False)
        else:
            await ctx.respond(embed=BotEmbed.rpg(f'{user_dc.name}的裝備包包','背包空無一物'))


    @equip.command(description='售出裝備給RPG商店（開發中）')
    async def sell(self,ctx,
                   equipment_uid:discord.Option(str,name='裝備uid',description='要售出的裝備')):
        equipment_uid = int(equipment_uid)
        item = sclient.get_rpgplayer_equipment(ctx.author.id,equipment_uid)
        
        if not item:
            await ctx.respond(f"{ctx.author.mention}：你沒有此件裝備")
            return
        
        sclient.sell_rpgplayer_equipment(ctx.author.id,equipment_uid)
        sclient.update_coins(ctx.author.id,"add",Coins.RCOIN,item.price)
        await ctx.respond(f"{ctx.author.mention}：已售出 {item.name} 並獲得 ${item.price}")

    @equip.command(description='售出同類型裝備給RPG商店（開發中）')
    async def bulksell(self,ctx,
                   equipment_id:discord.Option(str,name='裝備id',description='要售出的裝備')):
        equipment_id = int(equipment_id)
        items = sclient.get_rpgplayer_equipment(ctx.author.id,equipment_id=equipment_id)
        
        if not items:
            await ctx.respond(f"{ctx.author.mention}：你沒有此種裝備")
            return
        
        price = sclient.sell_rpgplayer_equipment(ctx.author.id,equipment_id=equipment_id)
        if price:
            sclient.update_coins(ctx.author.id,"add",Coins.RCOIN,price)
            await ctx.respond(f"{ctx.author.mention}：已批量售出 {items[0].name} 並獲得 ${price}")
        else:
            await ctx.respond(f"{ctx.author.mention}：沒有找到此種裝備")

    @equip.command(description='穿脫裝備（開發中）')
    async def waring(self,ctx,
                   equipment_uid:discord.Option(str,name='裝備uid',description='要穿/脫/換上的裝備')):
        equipment_uid = int(equipment_uid)
        item = sclient.get_rpgplayer_equipment(ctx.author.id,equipment_uid)

        if not item:
            await ctx.respond(f"{ctx.author.mention}：你沒有此件裝備")
            return
        
        if item.slot == EquipmentSolt.none:
            waring_item = sclient.get_rpgplayer_equipment(ctx.author.id,slot_id=item.slot.value)
            sclient.update_rpgplayer_equipment_warning(ctx.author.id,item.equipment_uid,item.item_id)
            sclient.update_rpguser_attribute(ctx.author.id,item.maxhp,item.atk,item.df,item.hrt,item.dex)
            if not waring_item:
                await ctx.respond(f"{ctx.author.mention}：已穿上 {item.customized_name or item.name}")
            else:
                sclient.update_rpgplayer_equipment_warning(ctx.author.id,waring_item.equipment_uid,None)
                sclient.update_rpguser_attribute(ctx.author.id,-waring_item.maxhp,-waring_item.atk,-waring_item.df,-waring_item.hrt,-waring_item.dex)
                await ctx.respond(f"{ctx.author.mention}：已將 {waring_item.customized_name or waring_item.name} 替換成 {item.customized_name or item.name}")
        
        else:
            sclient.update_rpgplayer_equipment_warning(ctx.author.id,item.equipment_uid,None)
            sclient.update_rpguser_attribute(ctx.author.id,-item.maxhp,-item.atk,-item.df,-item.hrt,-item.dex)
            await ctx.respond(f"{ctx.author.mention}：已脫下 {item.customized_name or item.name}")
        
    @equip.command(description='檢查裝備資訊（開發中）')
    async def check(self,ctx,
                   equipment_uid:discord.Option(str,name='裝備uid',description='要檢查的裝備')):
        item = sclient.get_rpgplayer_equipment(ctx.author.id,equipment_uid)
        
        if not item:
            await ctx.respond("你沒有此件裝備") 
            return
        
        embed = BotEmbed.rpg(item.customized_name if item.customized_name else item.name)
        embed.add_field(name="裝備uid",value=item.equipment_uid)
        embed.add_field(name="最大生命值",value=item.maxhp)
        embed.add_field(name="攻擊力",value=item.atk)
        embed.add_field(name="防禦力",value=item.df)
        embed.add_field(name="命中率(%)",value=item.hrt)
        embed.add_field(name="敏捷",value=item.dex)
        await ctx.respond(embed=embed)


def setup(bot):
    bot.add_cog(role_playing_game(bot))