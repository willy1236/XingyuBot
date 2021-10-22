import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension

with open('setting.json',mode='r',encoding='utf8') as jfile:
    jdata = json.load(jfile)

class crass_chat(Cog_Extension):
    #跨群聊天B5.1
    @commands.Cog.listener()
    async def on_message(self,msg):
        #for in_crass_chat_channel in jdata['crass_chat']:
        #    if msg.channel.id == in_crass_chat_channel:
        #        is_crass_chat = is_crass_chat +1
        if msg.author.bot == True:
            return
        elif msg.channel.id in set(jdata['crass_chat']):
            await msg.delete()
            crass_chat = jdata['crass_chat']

            embed=discord.Embed(description=f'{msg.content}',color=0x4aa0b5)
            embed.set_author(name=f'{msg.author}',icon_url=f'{msg.author.avatar_url}')
            embed.set_footer(text=f'來自: {msg.guild}')

            for crass_channel_id in crass_chat:
                channel = self.bot.get_channel(crass_channel_id)
                if channel != None:
                    await channel.send(embed=embed)

def setup(bot):
    bot.add_cog(crass_chat(bot))