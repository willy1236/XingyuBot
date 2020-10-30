import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension

with open('setting.json',mode='r',encoding='utf8') as jfile:
    jdata = json.load(jfile)

with open('command.json',mode='r',encoding='utf8') as jfile:
    comdata = json.load(jfile)

class crass_chat(Cog_Extension):
    #跨群聊天B4.0
    @commands.command()
    async def say(self,ctx,*,msg):
        await ctx.message.delete()
        #crass = ctx.channel
        crass_chat = jdata['crass_chat']
        send_channel = ctx.channel

        embed=discord.Embed(description=f'{msg}',color=0x4aa0b5)
        embed.set_author(name=f'{ctx.author.nick}',icon_url=f'{ctx.author.avatar_url}')
        embed.set_footer(text=f'{ctx.author} | {ctx.guild}')

        for b in crass_chat:
            if b == send_channel:
                for a in crass_chat:
                    channel = self.bot.get_channel(a)
                    await channel.send(embed=embed)
        
        #channel = self.bot.get_channel(int(jdata['crass.chat_軟啦']))
        #if channel != crass:
        #    await channel.send(embed=embed)

def setup(bot):
    bot.add_cog(crass_chat(bot))