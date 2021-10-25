import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension

class moderation(Cog_Extension):
    #clean
    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def clean(self,ctx,num:int):
        await ctx.channel.purge(limit=num+1)
        await ctx.send(content=f'清除完成，清除了{num}則訊息',delete_after=5)

def setup(bot):
    bot.add_cog(moderation(bot))