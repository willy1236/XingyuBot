import discord
from discord.ext import commands
import json
from lib.user import *
from core.classes import Cog_Extension
from library import BRS

jdata = json.load(open('setting.json',mode='r',encoding='utf8'))


class user_set(Cog_Extension):
    @commands.command()
    async def ui(self,ctx,user=None):
        user_dc = await find.user(ctx,user) or ctx.author
        user = User(user_dc.id)
        embed = BRS.simple(title=user_dc)
        embed.add_field(name='Pt點數',value=user.point.pt)
        await ctx.send(embed=embed)

def setup(bot):
    bot.add_cog(user_set(bot))