import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension

jdata = json.load(open('setting.json',mode='r',encoding='utf8'))

class debug(Cog_Extension):
    @commands.command()
    @commands.is_owner()
    async def embed(self,ctx,msg):
        embed=discord.Embed(title="Bot Radio Station",description=f'{msg}',color=0xc4e9ff)
        embed.set_footer(text='廣播電台 | 機器人全群公告')
        
        channel = self.bot.get_channel(870936349023285268)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.is_owner()
    async def debug(self,ctx):
        print(jdata['crass_chat'])

def setup(bot):
    bot.add_cog(debug(bot))