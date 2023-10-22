import discord,asyncio,random,datetime
from core.classes import Cog_Extension
from discord.ext import commands
from discord.commands import SlashCommandGroup
from starcord import sqldb,BotEmbed,sclient
from starcord.ui_element.RPGbutton import RPGbutton1,RPGbutton2

class role_playing_game(Cog_Extension):
    #work = SlashCommandGroup("work", "工作相關指令")
    
    @commands.slash_command(description='進行冒險（開發中）')
    async def advance(self,ctx:discord.ApplicationContext):
        # await ctx.respond('敬請期待',ephemeral=False)
        # return
        await ctx.respond(view=RPGbutton1(ctx.author.id))

    @commands.slash_command(description='進行工作（開發中）')
    async def work(self,ctx:discord.ApplicationContext):
        dbdata = sqldb.get_activities(ctx.author.id)
        if dbdata.get("work_date") == datetime.date.today():
            await ctx.respond("今天已經工作過了")
        
        await ctx.respond(view=RPGbutton2(ctx.author.id))

    @commands.slash_command(description='查看用戶資訊')
    async def ui(self,ctx:discord.ApplicationContext,user_dc:discord.Option(discord.Member,name='用戶',description='留空以查詢自己',default=None)):
        user_dc = user_dc or ctx.author
        user = sclient.get_dcuser(user_dc.id,True,user_dc)
        if not user:
            sqldb.create_user(user_dc.id)
            user = sclient.get_dcuser(user_dc.id,True,user_dc)

        pet = user.get_pet()
        pet_embed = pet.desplay() if pet else BotEmbed.simple(f'{user_dc.name} 的寵物','用戶沒有認養寵物')
        await ctx.respond(embeds=[user.desplay(self.bot), pet_embed])

    @commands.slash_command(description='查看背包（開發中）')
    async def bag(self,ctx:discord.ApplicationContext,user_dc:discord.Option(discord.Member,name='用戶',description='留空以查詢自己',default=None)):
        user_dc = user_dc or ctx.author
        data = sqldb.get_bag_desplay(user_dc.id)
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