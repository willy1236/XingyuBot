import discord,datetime
from discord.ext import commands
from core.classes import Cog_Extension
from BotLib.funtions import BRS
from BotLib.database import Database
from BotLib.basic import BotEmbed

class ScamChack:
    def __init__(self,text:str):
        self.text = text
        self.keyword =self.__keyword()

    def __keyword(self):
        keywords = ['Free','免費','Nitro','premiums-nitro','discerd.gift','disceord.gift']
        if self.text in keywords:
            return True
        else:
            return False


class event(Cog_Extension):
    cdata = Database().cdata
    voice_updata = False
    #跨群聊天Ver.1.0
    @commands.Cog.listener()
    async def on_message(self,msg):
        if msg.channel.id in self.cdata['crass_chat'] and not msg.author.bot:
            await msg.delete()

            embed=discord.Embed(description=f'{msg.content}',color=0x4aa0b5)
            embed.set_author(name=f'{msg.author}',icon_url=f'{msg.author.display_avatar.url}')
            embed.set_footer(text=f'來自: {msg.guild}')

            for i in self.cdata['crass_chat']:
                channel = self.bot.get_channel(i)
                if channel != None:
                    await channel.send(embed=embed)

    # @commands.Cog.listener()
    # async def send_bot_help():
    #     return

    @commands.Cog.listener()
    async def on_message(self, message):
        dict = {
            '抹茶粉':'由威立冠名贊助撥出~',
            '消費':'那你好像也是頂級消費者喔'
        }
        if message.content in dict and self.bot.user.id == 589744540240314368:
            await message.reply(dict[message.content])
        if message.content == '小幫手' or message.content== f'<@{self.bot.user.id}>':
            embed = BotEmbed.basic(self,f"你好~\n我是{self.bot.user.name}，是一個discord機器人喔~\n我的前輟是`!!`\n你可以輸入`!!help`來查看所有指令的用法\n\n希望我能在discord上幫助到你喔~")
            await message.reply(embed=embed)
        if self.bot.user in message.mentions:
            await BRS.mentioned(self,message)
        if message.mention_everyone == True:
            await BRS.mention_everyone(self,message)
        
        ScamChack = False
        if 'free' in message.content.lower() and 'nitro' in message.content.lower():
            ScamChack = True
        
        if ScamChack:
            await BRS.scam(self,message)
            #await message.delete()
            await message.reply('溫馨提醒:這可能是有關詐騙的訊息\n點擊連結前請先確認是否安全')
        
        if type(message.channel) == discord.channel.DMChannel:
            await BRS.dm(self,message)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.message_id == 640679249245634635:
            if str(payload.emoji) == '🍍':
                channel = self.bot.get_channel(706810474326655026)
                user = self.bot.get_user(payload.user_id)
                await channel.set_permissions(user,view_channel=True,reason='身分組選擇:加入')

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        if payload.message_id == 640679249245634635:
            if str(payload.emoji) == '🍍':
                channel = self.bot.get_channel(706810474326655026)
                user = self.bot.get_user(payload.user_id)
                await channel.set_permissions(user,overwrite=None,reason='身分組選擇:退出')
                    


    @commands.Cog.listener()
    async def on_voice_state_update(self,user, before, after):
            if self.voice_updata:
                NowTime = datetime.datetime.now()
                if before.channel and after.channel and before.channel != after.channel:
                    embed=discord.Embed(description=f'{user.mention} 更換語音',color=0x4aa0b5,timestamp=NowTime)
                elif not before.channel and after.channel:
                    embed=discord.Embed(description=f'{user.mention} 進入語音',color=0x4aa0b5,timestamp=NowTime)
                elif before.channel and not after.channel:
                    embed=discord.Embed(description=f'{user.mention} 離開語音',color=0x4aa0b5,timestamp=NowTime)
                else:
                    return
                embed.set_author(name=user,icon_url=user.display_avatar.url)

                if before.channel:
                    embed.set_footer(text=before.channel.guild.name)
                elif after.channel:
                    embed.set_footer(text=after.channel.guild.name)
                
                if before.channel:
                    embed.add_field(name='頻道', value=f'{before.channel.mention}', inline=False)
                if after.channel:
                    embed.add_field(name='頻道', value=f'{after.channel.mention}', inline=False)
                
                await self.bot.get_channel(950039715879464970).send(embed=embed)
            

def setup(bot):
    bot.add_cog(event(bot))