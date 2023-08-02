import discord,datetime,re
from discord.ext import commands
from core.classes import Cog_Extension
from starcord import Jsondb,BotEmbed,BRS,sqldb
#from .moderation import voice_lobby_list

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

voice_list = {
    613747262291443742: 631498685250797570,
    726790741103476746: 1021072271277834250
}

voice_lobby_list = [
    955475420042629140
]

keywords = {
    '抹茶粉':'由威立冠名贊助撥出~',
    '消費':'那你好像也是頂級消費者喔'
}

# dbdata = sqldb.get_notice_channel_by_type('crass_chat')
# crass_chat_channels = []
# for i in dbdata:
#     crass_chat_channels.append(i['channel_id'])

voice_updata = Jsondb.jdata.get('voice_updata')
debug_mode = Jsondb.jdata.get("debug_mode",True)

class event(Cog_Extension):    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        #被提及回報
        if self.bot.user in message.mentions and not await self.bot.is_owner(message.author):
            await BRS.mentioned(self.bot,message)
        #被提及所有人回報
        if message.mention_everyone and not await self.bot.is_owner(message.author):
            await BRS.mention_everyone(self.bot,message)
        
        #私人訊息回報
        if isinstance(message.channel,discord.DMChannel) and message.author != self.bot.user:
            await BRS.dm(self.bot,message)
            return

        #關鍵字觸發
        # if message.content in keywords and self.bot.user.id == 589744540240314368:
        #     await message.reply(keywords[message.content])
        #     return
        #介紹
        if message.content == self.bot.user.mention:
            embed = BotEmbed.basic(self.bot,description=f"你好~我是 dc小幫手，是一個discord機器人喔~\n你可以輸入 </help:1067700245015834638> 來查看所有指令的用法\n\n希望我能在discord上幫助到你喔~\n有任何建議與需求可以使用 </feedback:1067700244848058386> 指令")
            embed.set_footer(text="此機器人由 威立 負責維護")
            await message.reply(embed=embed)
            return
        
        if message.guild and message.guild.id == 613747262291443742 and not message.author.bot:
            p = re.compile(r'貢丸|贡丸|Meatball',re.IGNORECASE)
            result = p.search(message.content)
            if result:
                try:
                    await message.author.timeout_for(datetime.timedelta(seconds=60),"打出貢丸相關詞彙")
                    await message.delete(reason="打出貢丸相關詞彙")
                    await message.channel.send(f"{message.author} 貢丸很危險 不要打貢丸知道嗎")
                    channel = self.bot.get_channel(877495919879286824)
                    await channel.send(f"{message.author.mention} 打出了：{message.content}",allowed_mentions=False)
                except:
                    pass
            

        #詐騙檢查
        # ScamChack = False
        # if self.bot.user.id == 589744540240314368 and message.mention_everyone:
        #     text = message.content.lower()
        #     if 'free' in text and 'nitro' in text:
        #         ScamChack = True
        #     else:
        #         url = "https://spen.tk/api/v1/isMaliciousTerm"
        #         r = requests.get(url,params={'text':message.content}).json()
        #         if r.get('hasMatch',False):
        #             ScamChack = True
        #             matches = r.get('matches',None)

        # if ScamChack:
        #     await BRS.scam(self,message,matches)
        #     await message.delete()
        #     await message.channel.send('疑似為詐騙訊息，已自動刪除')

        #跨群聊天Ver.1.0
        # if not message.author.bot and message.channel.id in crass_chat_channels:
        #     await message.delete()

        #     embed=discord.Embed(description=message.content,color=0x4aa0b5)
        #     embed.set_author(name=message.author,icon_url=message.author.display_avatar.url)
        #     embed.set_footer(text=f'來自: {message.guild}')

        #     for i in crass_chat_channels:
        #         channel = self.bot.get_channel(i)
        #         if channel:
        #             await channel.send(embed=embed)
        #     return


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
    async def on_voice_state_update(self,user:discord.Member, before:discord.VoiceState, after:discord.VoiceState):
            def check(before, after):
                if before.channel:
                    guildid = before.channel.guild.id
                elif after.channel:
                    guildid = after.channel.guild.id
                else:
                    guildid = None

                if guildid in voice_list:
                    return guildid
                else:
                    return False

            if debug_mode:
               return
           
           #語音進出紀錄
            guildid = check(before,after)
            if voice_updata and guildid:
                NowTime = datetime.datetime.now()
                if before.channel and after.channel and before.channel != after.channel:
                    embed=discord.Embed(description=f'{user.mention} 更換語音',color=0x4aa0b5,timestamp=NowTime)
                elif not before.channel and after.channel:
                    embed=discord.Embed(description=f'{user.mention} 進入語音',color=0x4aa0b5,timestamp=NowTime)
                elif before.channel and not after.channel:
                    embed=discord.Embed(description=f'{user.mention} 離開語音',color=0x4aa0b5,timestamp=NowTime)
                else:
                    return
                
                username = user.name if user.discriminator == "0" else user
                embed.set_author(name=username,icon_url=user.display_avatar.url)
                embed.set_footer(text=self.bot.get_guild(guildid).name)
                
                if before.channel and after.channel:
                    embed.add_field(name='頻道', value=f'{before.channel.mention}->{after.channel.mention}', inline=False)
                elif before.channel:
                    embed.add_field(name='頻道', value=f'{before.channel.mention}', inline=False)
                elif after.channel:
                    embed.add_field(name='頻道', value=f'{after.channel.mention}', inline=False)
                
                await self.bot.get_channel(voice_list.get(guildid)).send(embed=embed)

            #動態語音
            if not before.channel and after.channel and after.channel.id in voice_lobby_list:
                guild = after.channel.guild
                category = after.channel.category
                #permission = discord.Permissions.advanced()
                #permission.manage_channels = True
                #overwrites = discord.PermissionOverwrite({user:permission})
                overwrites = {
                user: discord.PermissionOverwrite(manage_channels=True,manage_roles=True)
                }
                new_channel = await guild.create_voice_channel(name=f'{user.name}的頻道', reason='語音分流',category=category,overwrites=overwrites)
                await user.move_to(new_channel)

            #舞台發言
            if after.suppress and after.channel and after.channel.category and after.channel.category.id == 1097158160709591130 and (user.get_role(1126820808761819197) or user.get_role(1130849778264195104)):
                await user.request_to_speak()

    @commands.Cog.listener()
    async def on_member_remove(self, member:discord.Member):
        if debug_mode:
            return
        
        #離開通知
        guildid = str(member.guild.id)
        dbdata = sqldb.get_notice_channel(guildid,"member_leave")

        if dbdata:
            username = member.name if member.discriminator == "0" else f"{member.name}#{member.discriminator}"
            text = f'{member.mention} ({username}) 離開了我們'
            await self.bot.get_channel(dbdata["channel_id"]).send(text)

    @commands.Cog.listener()
    async def on_member_join(self, member:discord.Member):
        if debug_mode:
            return
        
        #加入通知
        guildid = str(member.guild.id)
        dbdata = sqldb.get_notice_channel(guildid,"member_join")

        if dbdata:
            username = member.name if member.discriminator == "0" else f"{member.name}#{member.discriminator}"
            text = f'{member.mention} ({username}) 加入了我們'
            await self.bot.get_channel(int(dbdata["channel_id"])).send(text)

        #警告系統：管理員通知
        notice_data = sqldb.get_notice_channel(guildid,"mod")
        mod_channel_id = notice_data.get('channel_id') if notice_data else None
        #role_id = notice_data['role_id']
        if mod_channel_id:
            dbdata = self.sqldb.get_warnings(str(member.id))
            #if role_id:
            #    role = member.guild.get_role(role_id)

            if dbdata:
                channel = self.bot.get_channel(mod_channel_id)
                channel.send(f"新成員{member.mention}({member.id}) 共有 {len(dbdata)} 個紀錄")

    @commands.Cog.listener()
    async def on_guild_join(self, guild:discord.Guild):
        report_channel = self.bot.get_channel(Jsondb.jdata['report_channel'])
        await report_channel.send(f"公會異動：我加入了 {guild.name} ({guild.id})")

    @commands.Cog.listener()
    async def on_guild_remove(self, guild:discord.Guild):
        report_channel = self.bot.get_channel(Jsondb.jdata['report_channel'])
        await report_channel.send(f"公會異動：我離開了 {guild.name} ({guild.id})")

def setup(bot):
    bot.add_cog(event(bot))