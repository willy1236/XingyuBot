import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension
import asyncio
import pyosu
from pyosu import OsuApi

with open('setting.json',mode='r',encoding='utf8') as jfile:
    jdata = json.load(jfile)


class osu(Cog_Extension):
    api = OsuApi('')

    @commands.command()
    async def map(self,ctx):
        pass    
    async def get_match(self,match_id='willy1236'):
        map = osu.beatmap_id
        print(map)
        print('1')

def setup(bot):
    bot.add_cog(osu(bot))