import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension

with open('setting.json',mode='r',encoding='utf8') as jfile:
    jdata = json.load(jfile)

with open('command.json',mode='r',encoding='utf8') as jfile:
    comdata = json.load(jfile)

class crass_chat(Cog_Extension):
    #跨群聊天B5.0
    @commands.Cog.listener()
    async def on_message(self,msg):
        if msg.author.bot == True:
            return

        is_crass_chat = 0
        for a in jdata['crass_chat']:
            if msg.channel.id == a:
                is_crass_chat = is_crass_chat +1
        
        if is_crass_chat >= 1:
            await msg.delete()
            crass_chat = jdata['crass_chat']

            embed=discord.Embed(description=f'{msg.content}',color=0x4aa0b5)
            if msg.author.nick == 'None':
                embed.set_author(name=f'{msg.author.name}',icon_url=f'{msg.author.avatar_url}')
            else:
                embed.set_author(name=f'{msg.author.nick}',icon_url=f'{msg.author.avatar_url}')
            embed.set_footer(text=f'{msg.author} | {msg.guild}')
            embed.set_footer(text=f'{msg.author} | {msg.guild}')

            for a in crass_chat:
                channel = self.bot.get_channel(a)
                await channel.send(embed=embed)


def setup(bot):
    bot.add_cog(crass_chat(bot))