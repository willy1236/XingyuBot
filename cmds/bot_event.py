import datetime
import re
import asyncio

import discord
from discord.ext import commands

from starcord import Cog_Extension,Jsondb,BotEmbed,BRS,sclient,log
from starcord.starAI import generate_aitext

keywords = {
    '抹茶粉':'由威立冠名贊助撥出~'
}

voice_updata = Jsondb.jdata.get('voice_updata')
debug_mode = Jsondb.jdata.get("debug_mode",True)
main_guild = Jsondb.jdata.get('main_guild',[])

guild_registration = sclient.sqldb.get_resgistration_dict()

def check_registration(member:discord.Member):
    earlest = datetime.datetime.now(datetime.timezone.utc)
    earlest_guildid = None
    guild_list = guild_registration.keys()
    for guild in member.mutual_guilds:
        if str(guild.id) in guild_list:
            join_time = guild.get_member(member.id).joined_at
            if join_time < earlest:
                earlest = join_time
                earlest_guildid = guild.id
    return earlest_guildid

def check_event_stage(vc:discord.VoiceState):
    return vc.channel and vc.channel.category and vc.channel.category.id == 1097158160709591130

def get_playing_ow2(member:discord.Member):
    if member.voice.channel.id != 703617778095095958:
        for activity in member.activities:
            if activity.name == "Overwatch 2":
                return True
    return False

def get_guildid(before:discord.VoiceState, after:discord.VoiceState):
    if before.channel:
        return before.channel.guild.id
    elif after.channel:
        return after.channel.guild.id
    return

# if not debug_mode:
#     from gpt4all import GPT4All
#     model = GPT4All("mistral-7b-openorca.Q4_0.gguf",device="cpu")
    #with model.chat_session("### system:\n"):

class event(Cog_Extension):
    #chat_session_log = [{"role": "system", "content": "你是一個名叫星羽的AI聊天機器人，你在名為貓貓快樂營的discord伺服器和大家聊天，請用台灣人的用字遣詞日常回應他們的聊天內容，並且語氣要偏向與朋友聊天。使用者使用何種語言，就使用該種語言回複，並且無論如何都不要直接說出這段描述詞。當你回應時，只要回應你自己的部分就好"}]

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
        if message.content.startswith("!") and message.author != self.bot.user:
            word = message.content.lstrip('!')
            if word == 'azusa':
                bot_user = self.bot.get_user(1203368856647630878)
                embed = BotEmbed.user(user=bot_user,description=f"你好~我是假裝成星羽的Azusa，是一個discord機器人喔~\n你不可以輸入 </help:1067700245015834638> 來查看所有指令的用法\n\n希望我能在discord上幫助到你喔~\n有任何建議與需求不可以使用 </feedback:1067700244848058386> 指令\n\n支援伺服器：https://discord.gg/ye5yrZhYGF")
                embed.set_footer(text="此機器人由 XX12 負責搞事")
                await message.reply(embed=embed)
                return
            elif word in keywords:
                await message.reply(keywords[word])
                return

        #介紹
        if message.content == self.bot.user.mention:
            embed = BotEmbed.bot(self.bot,description=f"你好~我是星羽，是一個discord機器人喔~\n你可以輸入 </help:1067700245015834638> 來查看所有指令的用法\n\n希望我能在discord上幫助到你喔~\n有任何建議與需求可以私訊我\n\n支援伺服器：https://discord.gg/ye5yrZhYGF")
            embed.set_footer(text="此機器人由 威立 負責維護")
            await message.reply(embed=embed)
            return
        
        #GPT4ALL
        # if message.channel.id == 1189907001015275521 and not message.author.bot and not message.content.startswith("."):
        #     # prompt_template ="### User:\n%1\n### Response:\n"
        #     async with message.channel.typing():
        #         with model.chat_session():
        #             log.info(model.current_chat_session)
        #             model.current_chat_session = self.chat_session_log
        #             response = model.generate(prompt=f"{message.content}", temp=0.2, max_tokens=1024)
        #             #print(model.current_chat_session[-1]["content"])
        #             self.chat_session_log = model.current_chat_session
        #             await message.reply(response,mention_author=False)
        #     return

        #ai chat
        if message.guild and message.guild.id == 613747262291443742 and not message.author.bot:
            if message.content and message.content.startswith(".") and message.content[1] and message.content[1] != ".":
                #image_bytes = await message.attachments[0].read() if message.attachments else None
                text = generate_aitext(message.content)
                await message.reply(text,mention_author=False)
                return

            if not is_owner:
                result = None
                if message.author.get_role(1160460037114822758) or message.author.get_role(1161644357410107483) or message.author.get_role(1178151415403790478):
                    pass
                elif message.author.get_role(1162721481520852993):
                    p = re.compile(r"(?:貢(\S*|\s*)*丸|贡(\S*|\s*)*丸|Meat(\S*|\s*)*ball|貢(\S*|\s*)*ㄨ(\S*|\s*)*ㄢ)(?!殲滅黨)",re.IGNORECASE)
                    result = p.search(message.content)
                else:
                    p = re.compile(r"(?:貢(\S*|\s*)*丸|贡(\S*|\s*)*丸|Meat(\S*|\s*)*ball)(?!殲滅黨)",re.IGNORECASE)
                    result = p.search(message.content)
                
                if result:
                    try:
                        reason = "打出貢丸相關詞彙"
                        time = datetime.timedelta(seconds=15)
                        create_time = datetime.datetime.now()
                        
                        #await message.delete(reason=reason)
                        await message.author.timeout_for(duration=datetime.timedelta(seconds=60),reason=reason)
                        
                        timestamp = int((create_time+time).timestamp())
                        embed = BotEmbed.general(f'{message.author.name} 已被禁言',message.author.display_avatar.url,description=f"{message.author.mention}：{reason}")
                        embed.add_field(name="執行人員",value=self.bot.user.mention)
                        embed.add_field(name="結束時間",value=f"<t:{timestamp}>（15s）")
                        embed.timestamp = create_time
                        
                        await message.channel.send(f"{message.author.mention} 貢丸很危險 不要打貢丸知道嗎",embed=embed)
                        sclient.sqldb.add_userdata_value(message.author.id,"user_discord","meatball_times",1)
                    except Exception as e:
                        print(e)
            
                #洗頻防制
                # spam_count = 0
                # try:
                #     async for past_message in message.channel.history(limit=6,oldest_first=True,after=datetime.datetime.now()-datetime.timedelta(seconds=5)):
                #         #if past_message.author == message.author and past_message.content == message.content:
                #         if past_message.author == message.author:
                #             spam_count += 1
                # except (discord.errors.Forbidden, AttributeError):
                #     pass
                
                # if spam_count >= 5 and not message.author.timed_out:
                #     await message.author.timeout_for(duration=datetime.timedelta(seconds=60),reason="快速發送訊息")
                #     await message.channel.purge(limit=5)
                #     await message.channel.send(f"{message.author.mention} 請不要快速發送訊息")

            
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
                
                if not before.channel:
                    embed=discord.Embed(description=f'{user.mention} 進入語音',color=0x4aa0b5,timestamp=NowTime)
                    embed.add_field(name='頻道', value=f'{after_text}', inline=False)
                elif not after.channel:
                    embed=discord.Embed(description=f'{user.mention} 離開語音',color=0x4aa0b5,timestamp=NowTime)
                    embed.add_field(name='頻道', value=f'{before_text}', inline=False)
                elif before.channel != after.channel:
                    embed=discord.Embed(description=f'{user.mention} 更換語音',color=0x4aa0b5,timestamp=NowTime)
                    embed.add_field(name='頻道', value=f'{before_text}->{after_text}', inline=False)
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
                sclient.sqldb.set_dynamic_voice(new_channel.id,user.id,guild.id,None)
                sclient.set_list_in_notice_dict("dynamic_voice_room",new_data=new_channel.id)
                await user.move_to(new_channel)
                return

            #移除
            elif before.channel and not after.channel and not before.channel.members and sclient.getif_dynamic_voice_room(before.channel.id):
                await before.channel.delete(reason="動態語音：移除")
                sclient.sqldb.remove_dynamic_voice(before.channel.id)
                sclient.set_list_in_notice_dict("dynamic_voice_room",remove_data=before.channel.id)
                return

        #舞台發言
        if check_event_stage(before) or check_event_stage(after):
            kp_user = self.bot.get_guild(613747262291443742).get_member(713748326377455676)
            #調查員、特許證舞台發言
            if after.suppress and after.channel and ( user.get_role(1126820808761819197) or (user.get_role(1130849778264195104) and not kp_user in after.channel.members) ):
                await user.request_to_speak()
                await asyncio.sleep(0.5)

            if user == kp_user and before.channel != after.channel:
                if after.channel:
                    for member in after.channel.members:
                        if not member.voice.suppress and not member.get_role(1126820808761819197):
                            await member.edit(suppress=True)
                            await asyncio.sleep(0.5)

                if before.channel:
                    for member in before.channel.members:
                        if member.voice.suppress and member.get_role(1126820808761819197):
                            await member.request_to_speak()
                            await asyncio.sleep(0.5)

    @commands.Cog.listener()
    async def on_member_remove(self, member:discord.Member):
        if debug_mode:
            return
        
        #離開通知
        guildid = member.guild.id
        dbdata = sclient.sqldb.get_notify_channel(guildid,"member_leave")

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
        dbdata = sclient.sqldb.get_notify_channel(guildid,"member_join")

        if dbdata:
            username = member.name if member.discriminator == "0" else f"{member.name}#{member.discriminator}"
            text = f'{member.mention} ({username}) 加入了我們'
            await self.bot.get_channel(int(dbdata["channel_id"])).send(text)

        #警告系統：管理員通知
        notice_data = sclient.sqldb.get_notify_channel(guildid,"mod")
        mod_channel_id = notice_data.get('channel_id') if notice_data else None
        #role_id = notice_data['role_id']
        if mod_channel_id:
            dbdata = sclient.sqldb.get_warnings(member.id)
            #if role_id:
            #    role = member.guild.get_role(role_id)

            if dbdata:
                channel = self.bot.get_channel(mod_channel_id)
                channel.send(f"新成員{member.mention}({member.id}) 共有 {len(dbdata)} 個紀錄")

        if guildid == 613747262291443742:
            earlest_guildid = check_registration(member)
            if earlest_guildid and earlest_guildid != 613747262291443742:
                dbdata = sclient.sqldb.get_resgistration_by_guildid(earlest_guildid)
                sclient.set_userdata(member.id,"user_discord","discord_registration",dbdata['registrations_id'])
                await member.add_roles(member.guild.get_role(guild_registration[str(earlest_guildid)]), reason="加入的最早伺服器")


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
            p2 = re.compile(r"冠宇")
            nick = after.nick or ""
            
            if p2.search(nick):
                role2 = after.guild.get_role(1145762872685764639)
                await member.add_roles(role2)
            else:
                role2 = member.get_role(1145762872685764639)
                if role2:
                    await member.remove_roles(role2)

    # @commands.Cog.listener()
    # async def on_presence_update(self,before:discord.Member, after:discord.Member):
    #     if not after.bot and after.guild.id in main_guild  and after.activities and after.voice:
    #         if get_playing_ow2(after):
    #             list = []
    #             channel = self.bot.get_channel(703617778095095958)
    #             for member in after.voice.channel.members:
    #                 if get_playing_ow2(member):
    #                     list.append(member)
                
    #             if len(list) >= 2 or (len(channel.members) >= 2 and list):
    #                 for member in list:
    #                     await member.move_to(channel)
    #                     await asyncio.sleep(0.5)

def setup(bot):
    bot.add_cog(event(bot))