import asyncio
import re
import os
from datetime import datetime,timezone,timedelta

import discord
from discord.ext import commands

from starlib import Jsondb,BotEmbed,sclient,log
from starlib.uiElement.view import WelcomeView, ReactionRole1, PollView
from ..extension import Cog_Extension

keywords = {
    '抹茶粉':'由威立冠名贊助撥出~'
}

member_names = {
    419131103836635136: "威立",
    1094928831976050728: "拔辣",
    702476284844048434: "諷黎",
    465831362168094730: "XX12",
    490136735557222402: "海豹",
    528935362199027716: "黑龍",
    814846401501986818: "黑龍",
}

voice_updata = Jsondb.config.get('voice_updata')
debug_mode = Jsondb.config.get("debug_mode",True)
main_guilds = Jsondb.config.get('main_guilds',[])

guild_registration = sclient.sqldb.get_resgistration_dict() if sclient.sqldb else {}

def check_registration(member:discord.Member):
    earlest = datetime.now(timezone.utc)
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

def check_spam(message:discord.Message, user_id:int):
    return message.author.id == user_id

config = Jsondb.config

class event(Cog_Extension):
    @commands.Cog.listener()
    async def on_ready(self):
        bot = self.bot
        log.info(f">> Bot online as {bot.user.name} <<")
        log.info(f">> Discord's version: {discord.__version__} <<")
        if bot.debug_mode:
            await bot.change_presence(activity=discord.Game(name="開發模式啟用中"),status=discord.Status.dnd)
            log.info(f">> Development mode: On <<")
        else:
            await bot.change_presence(activity=discord.Game(name=config.get("activity","/help")),status=discord.Status.online)

        if len(os.listdir('./cmds'))-1 == len(bot.cogs):
            log.info(">> Cogs all loaded <<")
        else:
            log.warning(f">> Cogs not all loaded, {len(bot.cogs)}/{len(os.listdir('./cmds'))} loaded<<")
        
        if bot.bot_code == 'Bot1' and not bot.debug_mode:
            #將超過28天的投票自動關閉
            dbdata = sclient.sqldb.get_all_active_polls()
            now = datetime.now()
            for poll in dbdata:
                if now - poll['created_at'] > timedelta(days=28):
                    sclient.sqldb.update_poll(poll['poll_id'],"is_on",0)
                else:   
                    bot.add_view(PollView(poll['poll_id'],sqldb=sclient.sqldb,bot=bot))

            invites = await bot.get_guild(613747262291443742).invites()
            now = datetime.now(timezone.utc)
            days_5 = timedelta(days=5)
            for invite in invites:
                if not invite.expires_at and not invite.scheduled_event and invite.uses == 0 and now - invite.created_at > days_5 and invite.url != "https://discord.gg/ye5yrZhYGF":
                    await invite.delete()
                    await asyncio.sleep(1)

            bot.add_view(WelcomeView())
            bot.add_view(ReactionRole1())

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        is_owner = await self.bot.is_owner(message.author)

        #被提及回報
        if self.bot.user in message.mentions and not is_owner:
            await self.bot.mentioned(self.bot,message)
        #被提及所有人回報
        if message.mention_everyone and not is_owner:
            await self.bot.mention_everyone(self.bot,message)
        
        #私人訊息回報
        if isinstance(message.channel,discord.DMChannel) and message.author != self.bot.user:
            await self.bot.dm(self.bot,message)
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
            await message.reply(embed=self.bot.about_embed())
            return

        #ai chat
        if message.guild and message.guild.id in [613747262291443742, 566533708371329024] and not message.author.bot:
            if message.content and message.content.startswith(".") and len(message.content) > 1 and message.content[1] != ".":
                #image_bytes = await message.attachments[0].read() if message.attachments else None
                text = sclient.starai.generate_aitext(f"{member_names.get(message.author.id,message.author.name)}：{message.content[1:]}")
                await message.reply(text,mention_author=False)
                return

            if not is_owner and message.guild.id == 613747262291443742:
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
                        #await message.delete(reason=reason)
                        await message.author.timeout_for(duration=timedelta(seconds=60),reason=reason)
                        
                        embed = BotEmbed.simple_warn_sheet(message.author,self.bot.user,reason=reason)
                        await message.channel.send(f"{message.author.mention} 貢丸很危險 不要打貢丸知道嗎",embed=embed)
                        sclient.sqldb.add_userdata_value(message.author.id,"user_discord","meatball_times",1)
                    except Exception as e:
                        print(e)
            
                #洗頻防制
                # spam_count = 0
                # try:
                #     now = datetime.now()
                #     async for past_message in message.channel.history(limit=6, oldest_first=True, after=now-timedelta(seconds=3)):
                #         if past_message.author == message.author:
                #             spam_count += 1

                #     if spam_count >= 5 and not message.author.timed_out:
                #         await message.author.timeout_for(duration=timedelta(seconds=60),reason="快速發送訊息")
                #         if message.channel.last_message.author != self.bot.user:
                #             await message.channel.purge(limit=10,check=lambda message, user_id=message.author.id: check_spam(message, user_id), around=now)
                #             await message.channel.send(f"{message.author.mention} 請不要快速發送訊息")
                # except (discord.errors.Forbidden, AttributeError):
                #     pass

            
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
            voice_log_dict = sclient.cache["voice_log"]
            if guildid in voice_log_dict:
                NowTime = datetime.now()
                before_text = ""
                after_text = ""
                if before.channel:
                    before_text = before.channel.mention if not sclient.cache.getif_dynamic_voice_room(before.channel.id) else before.channel.name + ' (動態語音)'
                if after.channel:
                    after_text = after.channel.mention if not sclient.cache.getif_dynamic_voice_room(after.channel.id) else after.channel.name + ' (動態語音)'
                
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
                embed.set_footer(text=user.guild.name)
                
                await self.bot.get_channel(voice_log_dict.get(guildid)[0]).send(embed=embed)
            
        #動態語音
        dynamic_voice_dict = sclient.cache["dynamic_voice"]
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
                sclient.cache.update_dynamic_voice_room(add_channel=new_channel.id)
                sclient.sqldb.set_dynamic_voice(new_channel.id,user.id,guild.id,None)
                await user.move_to(new_channel)
                return

            #移除
            elif before.channel and not after.channel and not before.channel.members and sclient.cache.getif_dynamic_voice_room(before.channel.id):
                await before.channel.delete(reason="動態語音：移除")
                sclient.cache.update_dynamic_voice_room(remove_channel=before.channel.id)
                sclient.sqldb.remove_dynamic_voice(before.channel.id)
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
                sclient.sqldb.set_userdata(member.id,"user_discord","discord_registration",dbdata['registrations_id'])
                await member.add_roles(member.guild.get_role(guild_registration[str(earlest_guildid)]), reason="加入的最早伺服器")


    @commands.Cog.listener()
    async def on_guild_join(self, guild:discord.Guild):
        report_channel = self.bot.get_channel(Jsondb.config.get('report_channel'))
        await report_channel.send(f"公會異動：我加入了 {guild.name} ({guild.id})")

    @commands.Cog.listener()
    async def on_guild_remove(self, guild:discord.Guild):
        report_channel = self.bot.get_channel(Jsondb.config.get('report_channel'))
        await report_channel.send(f"公會異動：我離開了 {guild.name} ({guild.id})")

    @commands.Cog.listener()
    async def on_member_update(self,before:discord.Member, after:discord.Member):
        guildid = after.guild.id
        member = after
        if guildid in main_guilds and (after.nick and before.nick != after.nick) or not after.nick:
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
    #     if not after.bot and after.guild.id in main_guilds  and after.activities and after.voice:
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