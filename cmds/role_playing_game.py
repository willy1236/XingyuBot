import discord
from core.classes import Cog_Extension
from discord.ext import commands

from bothelper.interface import UserClient
from bothelper import BotEmbed,sqldb

class RPGbutton1(discord.ui.View):
    def __init__(self,userid):
        super().__init__()
        self.userid = userid

    @discord.ui.button(label="按我進行冒險",style=discord.ButtonStyle.green)
    async def button_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user.id == self.userid:
            user = UserClient.get_rpguser(interaction.user.id)
            result = user.advance()

            await interaction.response.edit_message(content=result)
            #await interaction.response.send_message(content=result, ephemeral=False)

class RPGbutton2(discord.ui.View):
    def __init__(self,userid):
        super().__init__()
        self.userid = userid

    @discord.ui.button(label="按我進行工作",style=discord.ButtonStyle.green)
    async def button_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user.id == self.userid:
            user = UserClient.get_rpguser(interaction.user.id)
            result = user.work()

            await interaction.response.edit_message(content=result)

class role_playing_game(Cog_Extension):
    @commands.slash_command(description='進行冒險（開發中）')
    async def advance(self,ctx):
        # await ctx.respond('敬請期待',ephemeral=False)
        # return
        await ctx.respond(view=RPGbutton1(ctx.user.id))

    @commands.slash_command(description='進行工作（開發中）')
    async def work(self,ctx):
        # await ctx.respond('敬請期待',ephemeral=False)
        # return
        await ctx.respond(view=RPGbutton2(ctx.user.id))

    @commands.slash_command(description='查看用戶資訊（開發中）')
    async def ui(self,ctx,user_dc:discord.Option(discord.Member,name='用戶',description='留空以查詢自己',default=None)):
        user_dc = user_dc or ctx.author
        user = self.sqldb.get_user(str(user_dc.id))
        embed = user.desplay()
        embed.set_author(name=user_dc.name,icon_url=user_dc.avatar)
        await ctx.respond(embed=embed)

    @commands.slash_command(description='查看背包')
    async def bag(self,ctx,user_dc:discord.Option(discord.Member,name='用戶',description='留空以查詢自己',default=None)):
        user_dc = user_dc or ctx.author
        data = sqldb.get_bag_desplay(user_dc.id)
        embed = BotEmbed.general(f'{user_dc.name}的包包')
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