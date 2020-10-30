import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension

with open('command.json',mode='r',encoding='utf8') as jfile:
    comdata = json.load(jfile)

class random_squod(Cog_Extension):
    @commands.command()
    async def rand_squod(self,ctx):
        pass

def setup(bot):
    bot.add_cog(random_squod(bot))