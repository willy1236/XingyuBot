import discord,datetime,re
from discord.ext import commands
from core.classes import Cog_Extension
from starcord import Jsondb,BotEmbed,BRS,sqldb,sclient

keywords = {
    '抹茶粉':'由威立冠名贊助撥出~',
    '消費':'那你好像也是頂級消費者喔'
}

voice_updata = Jsondb.jdata.get('voice_updata')
debug_mode = Jsondb.jdata.get("debug_mode",True)
main_guild = Jsondb.jdata.get('main_guild',[])

class event(Cog_Extension):
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        is_owner = await self.bot.is_owner(message.author)
        #被提及回報
        if self.bot.user in message.mentions and not is_owner:
            await BRS.mentioned(self.bot,message)
        #被提及所有人回報
        if message.mention_everyone and not is_owner:
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
        
        if message.guild and message.guild.id == 613747262291443742 and not message.author.bot and not is_owner:
            p = re.compile(r'貢丸|贡丸|Meatball',re.IGNORECASE)
            result = p.search(message.content)
            if result:
                try:
                    await message.delete(reason="打出貢丸相關詞彙")
                    await message.author.timeout_for(duration=datetime.timedelta(seconds=60),reason="打出貢丸相關詞彙")
                    await message.channel.send(f"{message.author.mention} 貢丸很危險 不要打貢丸知道嗎")
                    sqldb.add_userdata_value(message.author.id,"user_discord","meatball_times",1)
                    channel = self.bot.get_channel(877495919879286824)
                    await channel.send(f"{message.author.name} 打出了：{message.content}")
                except Exception as e:
                    print(e)
        
            #洗頻防制
            spam_count = 0
            try:
                async for past_message in message.channel.history(limit=6,oldest_first=True,after=datetime.datetime.now()-datetime.timedelta(seconds=10)):
                    #if past_message.author == message.author and past_message.content == message.content:
                    if past_message.author == message.author:
                        spam_count += 1
            except discord.errors.Forbidden:
                pass
            
            if spam_count >= 5 and not message.author.timed_out:
                await message.author.timeout_for(duration=datetime.timedelta(seconds=60),reason="發送多次重複訊息")
                await message.channel.purge(limit=5)
                await message.channel.send(f"{message.author.mention} 請不要發送重複訊息")
                
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
        def get_guildid(before, after):
            if before.channel:
                return before.channel.guild.id
            elif after.channel:
                return after.channel.guild.id
            else:
                return None

        if debug_mode:
            return

        guildid = get_guildid(before,after)
        #語音進出紀錄
        if voice_updata:
            voice_log_dict = sclient.get_notice_dict("voice_log")
            if guildid in voice_log_dict:
                NowTime = datetime.datetime.now()
                before_text = ""
                after_text = ""
                if before.channel:
                    before_text = before.channel.mention if not sclient.getif_dynamic_voice_room(before.channel.id) else before.channel.name + ' (動態語音)'
                if after.channel:
                    after_text = after.channel.mention if not sclient.getif_dynamic_voice_room(after.channel.id) else after.channel.name + ' (動態語音)'
                
                if before.channel and after.channel and before.channel != after.channel:
                    embed=discord.Embed(description=f'{user.mention} 更換語音',color=0x4aa0b5,timestamp=NowTime)
                    embed.add_field(name='頻道', value=f'{before_text}->{after_text}', inline=False)
                
                elif not before.channel:
                    embed=discord.Embed(description=f'{user.mention} 進入語音',color=0x4aa0b5,timestamp=NowTime)
                    embed.add_field(name='頻道', value=f'{after_text}', inline=False)
                
                elif not after.channel:
                    embed=discord.Embed(description=f'{user.mention} 離開語音',color=0x4aa0b5,timestamp=NowTime)
                    embed.add_field(name='頻道', value=f'{before_text}', inline=False)
                
                else:
                    return
                
                username = user.name if user.discriminator == "0" else user
                embed.set_author(name=username,icon_url=user.display_avatar.url)
                embed.set_footer(text=self.bot.get_guild(guildid).name)
                
                await self.bot.get_channel(voice_log_dict.get(guildid)[0]).send(embed=embed)
            
            #動態語音
            dynamic_voice_dict = sclient.get_notice_dict("dynamic_voice")
            if guildid in dynamic_voice_dict:
                #新增
                if after.channel and after.channel.id == dynamic_voice_dict[guildid][0]:
                    guild = after.channel.guild
                    category = after.channel.category
                    #permission = discord.Permissions.advanced()
                    #permission.manage_channels = True
                    #overwrites = discord.PermissionOverwrite({user:permission})
                    overwrites = {
                    user: discord.PermissionOverwrite(manage_channels=True,manage_roles=True)
                    }
                    new_channel = await guild.create_voice_channel(name=f'{user.name}的頻道', reason='動態語音：新增',category=category,overwrites=overwrites)
                    sclient.set_dynamic_voice(new_channel.id,user.id,guild.id,None)
                    sclient.set_list_in_notice_dict("dynamic_voice_room",new_data=new_channel.id)
                    await user.move_to(new_channel)

                #移除
                elif before.channel and not after.channel and sclient.getif_dynamic_voice_room(before.channel.id) and not before.channel.members:
                    await before.channel.delete(reason="動態語音：移除")
                    sclient.remove_dynamic_voice(before.channel.id)
                    sclient.set_list_in_notice_dict("dynamic_voice_room",remove_data=before.channel.id)

            #舞台發言
            if after.suppress and after.channel and after.channel.category and after.channel.category.id == 1097158160709591130 and (user.get_role(1126820808761819197) or user.get_role(1130849778264195104)):
                await user.request_to_speak()

    @commands.Cog.listener()
    async def on_member_remove(self, member:discord.Member):
        if debug_mode:
            return
        
        #離開通知
        guildid = member.guild.id
        dbdata = sclient.get_notice_channel(guildid,"member_leave")

        if dbdata:
            username = member.name if member.discriminator == "0" else f"{member.name}#{member.discriminator}"
            text = f'{member.mention} ({username}) 離開了我們'
            await self.bot.get_channel(dbdata["channel_id"]).send(text)

    @commands.Cog.listener()
    async def on_member_join(self, member:discord.Member):
        if debug_mode:
            return
        
        #加入通知
        guildid = member.guild.id
        dbdata = sclient.get_notice_channel(guildid,"member_join")

        if dbdata:
            username = member.name if member.discriminator == "0" else f"{member.name}#{member.discriminator}"
            text = f'{member.mention} ({username}) 加入了我們'
            await self.bot.get_channel(int(dbdata["channel_id"])).send(text)

        #警告系統：管理員通知
        notice_data = sclient.get_notice_channel(guildid,"mod")
        mod_channel_id = notice_data.get('channel_id') if notice_data else None
        #role_id = notice_data['role_id']
        if mod_channel_id:
            dbdata = self.sqldb.get_warnings(member.id)
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

    @commands.Cog.listener()
    async def on_member_update(self,before:discord.Member, after:discord.Member):
        guildid = after.guild.id
        member = after
        if guildid in main_guild and (after.nick and before.nick != after.nick) or not after.nick:
            p1 = re.compile(r"貢丸")
            p2 = re.compile(r"冠宇")
            nick = after.nick or ""
            if p1.search(nick):
                role1 = after.guild.get_role(1136338119835254946)
                await member.add_roles(role1)
            else:
                role1 = member.get_role(1136338119835254946)
                if role1:
                    await member.remove_roles(role1)
            
            if p2.search(nick):
                role2 = after.guild.get_role(1145762872685764639)
                await member.add_roles(role2)
            else:
                role2 = member.get_role(1145762872685764639)
                if role2:
                    await member.remove_roles(role2)

    @commands.Cog.listener()
    async def on_presence_update(self,before:discord.Member, after:discord.Member):
        if after.guild.id in main_guild and not after.bot and after.activity and after.voice.channel:
            if after.activity.name == "Overwatch 2" and after.voice.channel.id != 703617778095095958:
                channel = self.bot.get_channel(703617778095095958)
                await after.move_to(channel)

def setup(bot):
    bot.add_cog(event(bot))