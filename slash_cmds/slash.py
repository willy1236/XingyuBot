import discord
from discord.ext import commands
import random,asyncio
from discord.commands import SlashCommandGroup

from BotLib.funtions import find,converter,random_color,BRS
from core.classes import Cog_Extension
from BotLib.database import Database
from BotLib.basic import BotEmbed

class slash(Cog_Extension):
    @commands.slash_command(description='向大家說哈瞜')
    async def hello(self,ctx, name: str = None):
        await ctx.defer()
        name = name or ctx.author.name
        await ctx.respond(f"Hello {name}!")

def setup(bot):
    bot.add_cog(slash(bot))
    