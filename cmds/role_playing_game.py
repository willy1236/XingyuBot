import discord
from core.classes import Cog_Extension
from discord.ext import commands

from BotLib.userlib import *
from BotLib.database import Database
from BotLib.basic import BotEmbed
from BotLib.funtions import find

class RPGbutton1(discord.ui.View):
    @discord.ui.button(label="按我進行一次冒險",style=discord.ButtonStyle.green)
    async def button_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        user = User(interaction.user.id)
        result = user.advance()
        await interaction.response.edit_message(content=result)
        #await interaction.response.send_message(content=result, ephemeral=False)

class role_playing_game(Cog_Extension):
    @commands.command()
    @commands.is_owner()
    async def advance(self,ctx):
        await ctx.send(view=RPGbutton1())
    

def setup(bot):
    bot.add_cog(role_playing_game(bot))