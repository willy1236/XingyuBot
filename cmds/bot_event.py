import discord,datetime,requests
from discord.ext import commands
from core.classes import Cog_Extension
from bothelper import Jsondb,BotEmbed,BRS

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

db = Jsondb
voice_updata = db.jdata.get('voice_updata',False)

voice_list = {
    613747262291443742: 631498685250797570,
    726790741103476746: 1021072271277834250
}

member_list = {
    613747262291443742: 613747262291443744
}

class event(Cog_Extension):
    #跨群聊天Ver.1.0
    @commands.Cog.listener()
    async def on_message(self,msg):
        cdata = Jsondb.cdata['crass_chat']
        if msg.channel.id in cdata and not msg.author.bot:
            await msg.delete()

            embed=discord.Embed(description=msg.content,color=0x4aa0b5)
            embed.set_author(name=msg.author,icon_url=msg.author.display_avatar.url)
            embed.set_footer(text=f'來自: {msg.guild}')

            for i in cdata:
                channel = self.bot.get_channel(i)
                if channel:
                    await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message):
        dict = {
            '抹茶粉':'由威立冠名贊助撥出~',
            '消費':'那你好像也是頂級消費者喔'
        }
        #關鍵字觸發
        if message.content in dict and self.bot.user.id == 589744540240314368:
            await message.reply(dict[message.content])
        #介紹
        if message.content == '小幫手' or message.content == f'<@{self.bot.user.id}>':
            embed = BotEmbed.basic(self,f"你好~\n我是{self.bot.user.name}，是一個discord機器人喔~\n你可以輸入`/help`來查看所有指令的用法\n\n希望我能在discord上幫助到你喔~")
            await message.reply(embed=embed)
        #被提及回報
        if self.bot.user in message.mentions:
            await BRS.mentioned(self,message)
        #被提及所有人回報
        if message.mention_everyone:
            await BRS.mention_everyone(self,message)
        #詐騙檢查
        ScamChack = False
        if self.bot.user.id == 589744540240314368 and message.mention_everyone:
            if 'free' in message.content.lower() and 'nitro' in message.content.lower():
                ScamChack = True
            else:
                url = "https://spen.tk/api/v1/isMaliciousTerm"
                r = requests.get(url,params={'text':message.content}).json()
                if r.get('hasMatch',False):
                    ScamChack = True
                    matches = r.get('matches',None)

        if ScamChack:
            await BRS.scam(self,message,matches)
            await message.delete()
            await message.channel.send('疑似為詐騙訊息，已自動刪除')
        #私人訊息回報
        if isinstance(message.channel,discord.channel.DMChannel) and message.author != self.bot.user:
            await BRS.dm(self,message)

    # @commands.Cog.listener()
    # async def on_raw_reaction_add(self, payload):
    #     if payload.message_id == 640679249245634635:
    #         if str(payload.emoji) == '🍍':
    #             channel = self.bot.get_channel(706810474326655026)
    #             user = self.bot.get_user(payload.user_id)
    #             await channel.set_permissions(user,view_channel=True,reason='身分組選擇:加入')

    # @commands.Cog.listener()
    # async def on_raw_reaction_remove(self, payload):
    #     if payload.message_id == 640679249245634635:
    #         if str(payload.emoji) == '🍍':
    #             channel = self.bot.get_channel(706810474326655026)
    #             user = self.bot.get_user(payload.user_id)
    #             await channel.set_permissions(user,overwrite=None,reason='身分組選擇:退出')
                    
    @commands.Cog.listener()
    async def on_voice_state_update(self,user, before:discord.VoiceState, after:discord.VoiceState):
            def check(before, after):
                if before.channel:
                    guild = before.channel.guild.id
                elif after.channel:
                    guild = after.channel.guild.id
                else:
                    guild = None

                if guild in voice_list:
                    return guild
                else:
                    return False

            guildid = check(before,after)

            if voice_updata and self.bot.user.id == 589744540240314368 and guildid:
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
                
                if before.channel and after.channel:
                    embed.add_field(name='頻道', value=f'{before.channel.mention}->{after.channel.mention}', inline=False)
                elif before.channel:
                    embed.add_field(name='頻道', value=f'{before.channel.mention}', inline=False)
                elif after.channel:
                    embed.add_field(name='頻道', value=f'{after.channel.mention}', inline=False)
                
                await self.bot.get_channel(voice_list.get(guildid)).send(embed=embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        guildid = member.guild.id
        if guildid in member_list and self.bot.user.id == 589744540240314368:
            text = f'{member.mention} ({member.name}#{member.discriminator}) 離開了我們'
            await self.bot.get_channel(member_list.get(guildid)).send(text)

def setup(bot):
    bot.add_cog(event(bot))