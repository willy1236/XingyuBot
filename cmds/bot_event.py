import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension

jdata = json.load(open('setting.json',mode='r',encoding='utf8'))

class event(Cog_Extension):
    @commands.Cog.listener()
    async def send_bot_help():
        return

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.content == '小幫手':
            pass

def setup(bot):
    bot.add_cog(event(bot))