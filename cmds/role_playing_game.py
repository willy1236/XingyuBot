import discord
from core.classes import Cog_Extension
from discord.ext import commands

from BotLib.interface.user import *
from BotLib.database import Database
from BotLib.basic import BotEmbed
from BotLib.funtions import find

class RPGbutton1(discord.ui.View):
    @discord.ui.button(label="按我進行冒險",style=discord.ButtonStyle.green)
    async def button_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        user = User(interaction.user.id)
        result = user.advance()
        await interaction.response.edit_message(content=result)
        #await interaction.response.send_message(content=result, ephemeral=False)

class role_playing_game(Cog_Extension):
    @commands.slash_command(description='進行冒險（開發中）')
    async def advance(self,ctx):
        await ctx.respond('敬請期待',ephemeral=False)
        return
        await ctx.respond(view=RPGbutton1())

def setup(bot):
    bot.add_cog(role_playing_game(bot))