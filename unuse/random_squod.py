import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension


class random_squod(Cog_Extension):
    @commands.command()
    async def rand_squod(self,ctx):
        pass

def setup(bot):
    bot.add_cog(random_squod(bot))