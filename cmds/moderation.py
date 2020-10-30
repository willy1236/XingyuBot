import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension

with open('command.json',mode='r',encoding='utf8') as jfile:
    comdata = json.load(jfile)

class moderation(Cog_Extension):
    #clean
    @commands.command()
    @commands.is_owner()
    async def clean(self,ctx,num:int):
        await ctx.channel.purge(limit=num+1)

def setup(bot):
    bot.add_cog(moderation(bot))