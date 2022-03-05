import discord
from discord.ext import commands
import json
from core.classes import Cog_Extension
from library import BRS

jdata = json.load(open('setting.json',mode='r',encoding='utf8'))
cdata = json.load(open('database/channel_settings.json',mode='r',encoding='utf8'))
keywords = ['Free','免費','Nitro','premiums-nitro','discerd.gift','disceord.gift']
class event(Cog_Extension):
    #跨群聊天Ver.1.0
    @commands.Cog.listener()
    async def on_message(self,msg):
        if msg.channel.id in cdata['crass_chat'] and msg.author.bot == False:
            await msg.delete()

            embed=discord.Embed(description=f'{msg.content}',color=0x4aa0b5)
            embed.set_author(name=f'{msg.author}',icon_url=f'{msg.author.display_avatar.url}')
            embed.set_footer(text=f'來自: {msg.guild}')

            for i in cdata['crass_chat']:
                channel = self.bot.get_channel(i)
                if channel != None:
                    await channel.send(embed=embed)

    # @commands.Cog.listener()
    # async def send_bot_help():
    #     return

    @commands.Cog.listener()
    async def on_message(self, message):
        #if message.content == '小幫手':
        #    pass
        #if message.mention_everyone == True:
        #    await message.reply('你tag所有人了')
        if ('@everyone' in message.content or message.mention_everyone) and message.content in keywords:
            channel = self.bot.get_channel(message.channel.id)
            await BRS.scam(self,message)
            await message.delete()
            await channel.send('已刪除一條疑似詐騙的訊息')

def setup(bot):
    bot.add_cog(event(bot))