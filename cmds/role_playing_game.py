import discord,asyncio,random,datetime
from core.classes import Cog_Extension
from discord.ext import commands
from discord.commands import SlashCommandGroup
from starcord import BotEmbed,sclient,ChoiceList
from starcord.ui_element.RPGbutton import RPGbutton1,RPGbutton2
from starcord.models import GameInfoPage
from starcord.types import Coins

rpgcareer_option = ChoiceList.set("rpgcareer_option")

class role_playing_game(Cog_Extension):
    work = SlashCommandGroup("work", "工作相關指令")
    
    @commands.slash_command(description='進行冒險（開發中）')
    async def advance(self,ctx:discord.ApplicationContext):
        # await ctx.respond('敬請期待',ephemeral=False)
        # return
        await ctx.respond(view=RPGbutton1(ctx.author.id))

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
            reward_item_id = dbdata.get("reward_item_id")
            reward_item_name = dbdata.get("item_name")
            reward_item_min = dbdata.get("reward_item_min",0)
            reward_item_max = dbdata.get("reward_item_max",0)
            
            if reward_item_id:
                reward_item_get = random.randint(reward_item_min,reward_item_max)
                hard_woring_rate = (reward_item_get - reward_item_min) / (reward_item_max - reward_item_min) if reward_item_max != 0 else 0
                sclient.update_bag(rpguser.discord_id,reward_item_id,reward_item_get)
                
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

    @commands.slash_command(description='查看背包（開發中）')
    async def bag(self,ctx:discord.ApplicationContext,user_dc:discord.Option(discord.Member,name='用戶',description='留空以查詢自己',default=None)):
        user_dc = user_dc or ctx.author
        data = sclient.get_bag_desplay(user_dc.id)
        embed = BotEmbed.simple(f'{user_dc.name}的包包')
        if data:
            text = ""
            for item in data:
                text += f"{item['item_name']} x{item['amount']}\n"
            embed.add_field(name='一般物品',value=text)
        else:
            embed.add_field(name='一般物品',value='背包空無一物')
        await ctx.respond(embed=embed)

def setup(bot):
    bot.add_cog(role_playing_game(bot))