import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension

jdata = json.load(open('setting.json',mode='r',encoding='utf8'))

class crass_chat(Cog_Extension):
    #跨群聊天B5.1
    @commands.Cog.listener()
    async def on_message(self,msg):
        if msg.channel.id in set(jdata['crass_chat']) and msg.author.bot == False:
            await msg.delete()
            crass_chat = jdata['crass_chat']

            embed=discord.Embed(description=f'{msg.content}',color=0x4aa0b5)
            embed.set_author(name=f'{msg.author}',icon_url=f'{msg.author.avatar_url}')
            embed.set_footer(text=f'來自: {msg.guild}')

            for i in crass_chat:
                channel = self.bot.get_channel(crass_chat[i])
                if channel != None:
                    await channel.send(embed=embed)

def setup(bot):
    bot.add_cog(crass_chat(bot))