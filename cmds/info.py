import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension

with open('command.json',mode='r',encoding='utf8') as jfile:
    comdata = json.load(jfile)

class info(Cog_Extension):
    # info
    @commands.command()
    async def info(self, ctx, arg):
        if arg == 'help':
            await ctx.send(comdata['co.info'])

        if arg == 'crass_chat':
            await ctx.send(comdata['co.info.crass_chat'])
        
        if arg == 'vpn':
            await ctx.send(comdata['co.info.vpn'])
        if arg == 'vpn01':
            await ctx.send(comdata['co.info.vpn01'])

def setup(bot):
    bot.add_cog(info(bot))