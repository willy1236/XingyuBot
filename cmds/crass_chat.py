import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension

with open('setting.json',mode='r',encoding='utf8') as jfile:
    jdata = json.load(jfile)

with open('command.json',mode='r',encoding='utf8') as jfile:
    comdata = json.load(jfile)

class crass_chat(Cog_Extension):
    #跨群聊天B3.0
    @commands.command()
    async def say(self,ctx,arg):
        
        crass = ctx.channel

        embed=discord.Embed(description=f'{arg}',color=0x4aa0b5)
        embed.set_author(name=f'{ctx.author.nick}',icon_url=f'{ctx.author.avatar_url}')
        embed.set_footer(text=f'{ctx.author} | {ctx.guild}')

        channel = self.bot.get_channel(int(jdata['crass.chat_軟啦']))
        if channel != crass:
            await channel.send(embed=embed)

        channel = self.bot.get_channel(int(jdata['crass.chat_我就讚']))
        if channel != crass:
            await channel.send(embed=embed)

    #@commands.Cog.listener()
    #async def on_message(self,msg):
    #    crass_chat == [int(jdata['crass.chat_軟啦']),int(jdata['crass.chat_我就讚']),566533708371329026]
    #    if msg.channel.id == 566533708371329026 and msg.author != self.bot.user :
    #        await msg.channel.send('hi')

def setup(bot):
    bot.add_cog(crass_chat(bot))