import discord,asyncio,random,datetime
from core.classes import Cog_Extension
from discord.ext import commands
from discord.commands import SlashCommandGroup
from starcord import BotEmbed,sclient
from starcord.ui_element.RPGbutton import RPGbutton1,RPGbutton2
from starcord.models.model import GameInfoPage
from starcord.types import Coins

class role_playing_game(Cog_Extension):
    #work = SlashCommandGroup("work", "工作相關指令")
    
    @commands.slash_command(description='進行冒險（開發中）')
    async def advance(self,ctx:discord.ApplicationContext):
        # await ctx.respond('敬請期待',ephemeral=False)
        # return
        await ctx.respond(view=RPGbutton1(ctx.author.id))

    @commands.slash_command(description='進行工作（開發中）')
    async def work(self,ctx:discord.ApplicationContext):
        # dbdata = sclient.get_activities(ctx.author.id)
        # if dbdata.get("work_date") == datetime.date.today():
        #     await ctx.respond("今天已經工作過了")
        
        # await ctx.respond(view=RPGbutton2(ctx.author.id))
        dbdata = sclient.user_work(ctx.author.id)
        if dbdata:
            next_work = int((dbdata.get("last_work") + datetime.timedelta(hours=11)).timestamp())
            embed = BotEmbed.rpg("工作結果",f"你已經工作過了，請等到 <t:{next_work}> 再繼續工作")
        else:
            next_work = int((datetime.datetime.now() + datetime.timedelta(hours=11)).timestamp())
            scoin_add = random.randint(5,25)
            sclient.update_coins(ctx.author.id, "add", Coins.SCOIN, scoin_add)
            embed = BotEmbed.rpg("工作結果",f"你勤奮的打工，獲得 {scoin_add} 星幣\n下次工作時間：<t:{next_work}>")

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
                text += f"{item['name']} x{item['amount']}\n"
            embed.add_field(name='一般物品',value=text)
        else:
            embed.add_field(name='一般物品',value='背包空無一物')
        await ctx.respond(embed=embed)

def setup(bot):
    bot.add_cog(role_playing_game(bot))