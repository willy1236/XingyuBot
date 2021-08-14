import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension

with open('setting.json',mode='r',encoding='utf8') as jfile:
    jdata = json.load(jfile)

with open('command.json',mode='r',encoding='utf8') as jfile:
    comdata = json.load(jfile)

class event(Cog_Extension):
    @commands.Cog.listener()
    async def send_bot_help():
        return


def setup(bot):
    bot.add_cog(event(bot))