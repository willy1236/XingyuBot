import discord
from core.classes import Cog_Extension
from discord.ext import commands

from bothelper.interface import UserClient
from bothelper import BotEmbed,find

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

class role_playing_game(Cog_Extension):
    @commands.slash_command(description='進行冒險（開發中）')
    async def advance(self,ctx):
        # await ctx.respond('敬請期待',ephemeral=False)
        # return
        await ctx.respond(view=RPGbutton1(ctx.user.id))

def setup(bot):
    bot.add_cog(role_playing_game(bot))