import asyncio
import re
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands

from starlib import BotEmbed, Jsondb, log, sclient, tz
from starlib.database import DBCacheType, NotifyChannelType, PrivilegeLevel
from starlib.instance import *
from starlib.starAgent import ModelMessage, MyDeps, agent

from ..extension import Cog_Extension
from ..uiElement.view import PollView, ReactionRoleView, TicketChannelView, TicketLobbyView

keywords = {}

config = Jsondb.config
voice_updata = config.voice_updata

ai_access_guilds: list[int] = happycamp_guild + debug_guilds

guild_registration = sclient.sqldb.get_raw_registrations() if sclient.sqldb else {}

agent_history: dict[int, list[ModelMessage]] = {}


def check_registration(member: discord.Member):
    earlest = datetime.now(timezone.utc)
    earlest_guildid = None
    guild_list = guild_registration.keys()
    for guild in member.mutual_guilds:
        if guild.id in guild_list:
            join_time = guild.get_member(member.id).joined_at

            if join_time and join_time < earlest:
                earlest = join_time
                earlest_guildid = guild.id
    return earlest_guildid


def check_event_stage(vc: discord.VoiceState):
    return vc.channel and vc.channel.category and vc.channel.category.id == 1097158160709591130


def get_playing_ow2(member: discord.Member):
    if member.voice.channel.id != 703617778095095958:
        for activity in member.activities:
            if activity.name == "Overwatch 2":
                return True
    return False


def get_guildid(before: discord.VoiceState, after: discord.VoiceState):
    if before.channel:
        return before.channel.guild.id
    elif after.channel:
        return after.channel.guild.id
    return


def check_spam(message: discord.Message, user_id: int):
    return message.author.id == user_id


class event(Cog_Extension):
    @commands.Cog.listener()
    async def on_ready(self):
        bot = self.bot

        now = datetime.now(tz)
        if bot.bot_code == "1" and not bot.debug_mode:
            # 移除過期邀請
            invites = await bot.get_guild(happycamp_guild[0]).invites()
            days_7 = timedelta(days=7)
            for invite in invites:
                if not invite.expires_at and not invite.scheduled_event and invite.uses == 0 and invite.created_at and now - invite.created_at > days_7:
                    await invite.delete()
                    await asyncio.sleep(1)

        # 投票介面
        polls = sclient.sqldb.get_active_polls()
        days_poll_period = timedelta(days=28)
        for poll in polls:
            if now - poll.created_at > days_poll_period:
                # 將超過28天的投票自動關閉
                poll.end_at = now
                sclient.sqldb.merge(poll)
                log.debug("Ended poll: %s", poll.poll_id)
            else:
                bot.add_view(PollView(poll, sqldb=sclient.sqldb, bot=bot), message_id=poll.message_id)
                log.debug("Loaded poll: %s", poll.poll_id)

        # 反應身分組
        for react_message in sclient.sqldb.get_reaction_role_message_all():
            log.debug("Loading reaction role message: %s", react_message.message_id)
            channel = bot.get_channel(react_message.channel_id)
            if channel:
                assert isinstance(channel, discord.abc.Messageable)
                try:
                    message = await channel.fetch_message(react_message.message_id)
                    await asyncio.sleep(1)
                except discord.errors.NotFound:
                    message = channel.get_partial_message(react_message.message_id)
            else:
                message = None

            if message:
                react_roles = sclient.sqldb.get_reaction_roles_by_message(react_message.message_id)
                bot.add_view(ReactionRoleView(react_message.message_id, react_roles), message_id=react_message.message_id)
                log.debug("Loaded reaction role message: %s", react_message.message_id)
            elif not debug_mode:
                sclient.sqldb.delete_reaction_role_message(react_message.message_id)
                log.debug("Deleted reaction role message: %s", react_message.message_id)
        # 動態語音
        dynamic_voice_ids = sclient.sqldb.get_all_dynamic_voice()
        if dynamic_voice_ids:
            removed_ids = []
            for id in dynamic_voice_ids:
                channel = bot.get_channel(id)
                if not channel:
                    removed_ids.append(id)
                elif not channel.members:
                    await channel.delete(reason="動態語音：移除")
                    removed_ids.append(id)

            log.warning("Dynamic voice channels not found and deleted: %s", removed_ids)
            sclient.sqldb.batch_remove_dynamic_voice(removed_ids)

        # 私人頻道大廳
        ticket_lobbys = sclient.sqldb.get_all_ticket_lobbys()
        for lobby in ticket_lobbys:
            log.debug("Loading ticket lobby: %s", lobby.channel_id)
            channel = bot.get_channel(lobby.channel_id)
            if channel:
                assert isinstance(channel, discord.abc.Messageable)
                try:
                    message = await channel.fetch_message(lobby.message_id)
                    await asyncio.sleep(1)
                except discord.errors.NotFound:
                    message = channel.get_partial_message(lobby.message_id)
            else:
                message = None

            if message:
                bot.add_view(TicketLobbyView(channel.id), message_id=lobby.message_id)
                log.debug("Loaded ticket lobby: %s", lobby.channel_id)
            elif not debug_mode:
                sclient.sqldb.delete_ticket_lobby(lobby.channel_id)
                log.debug("Deleted ticket lobby: %s", lobby.channel_id)

        # 私人頻道
        active_tickets = sclient.sqldb.get_active_ticket_channels()
        for ticket in active_tickets:
            log.debug(f"Loading ticket channel: {ticket.channel_id}")
            channel = bot.get_channel(ticket.channel_id)
            if channel:
                bot.add_view(TicketChannelView(channel, bot.get_user(ticket.creator_id)), message_id=ticket.view_message_id)
                log.debug(f"Loaded ticket channel: {ticket.channel_id}")

        # Bot status
        log.info(f">> Bot online as {bot.user.name} <<")
        log.info(f">> Py-cord's version: {discord.__version__} <<")
        if bot.debug_mode:
            await bot.change_presence(activity=discord.CustomActivity(name="開發模式啟用中"), status=discord.Status.dnd)
            log.info(f">> Development mode: On <<")
        else:
            if config.activity is None:
                raise RuntimeError("Missing config key: activity")
            await bot.change_presence(activity=discord.CustomActivity(name=config.activity), status=discord.Status.online)

        cog_path = bot._COG_PATH
        total_cog_files = len([f for f in cog_path.iterdir() if f.is_file() and f.suffix == ".py"])
        if total_cog_files == len(bot.cogs):
            log.info(">> Cogs all loaded <<")
        else:
            log.warning(f">> Cogs not all loaded, {len(bot.cogs)}/{total_cog_files} loaded<<")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        is_owner = await self.bot.is_owner(message.author)

        if not is_owner:
            # 被提及回報
            if self.bot.user in message.mentions:
                await self.bot.mentioned(message)
            # 被提及所有人回報
            if message.mention_everyone and not message.author.bot:
                await self.bot.mention_everyone(message)

        #私人訊息回報
        if isinstance(message.channel,discord.DMChannel) and message.author != self.bot.user:
            await self.bot.dm(message)
            return

        #介紹
        if message.content == self.bot.user.mention:
            await message.reply(embed=self.bot.about_embed())
            return

        if message.guild and message.guild.id == happycamp_guild[0] and not message.author.bot:
            # 貢丸防制
            if not is_owner:
                if message.author.get_role(1160460037114822758) or message.author.get_role(1161644357410107483) or message.author.get_role(1178151415403790478):
                    result = None
                elif message.author.get_role(1162721481520852993):
                    p = re.compile(r"(?:貢(\S*|\s*)*丸|贡(\S*|\s*)*丸|Meat(\S*|\s*)*ball|貢(\S*|\s*)*ㄨ(\S*|\s*)*ㄢ)(?!殲滅黨)", re.IGNORECASE)
                    result = p.search(message.content)
                else:
                    p = re.compile(r"(?:貢(\S*|\s*)*丸|贡(\S*|\s*)*丸|Meat(\S*|\s*)*ball)(?!殲滅黨)", re.IGNORECASE)
                    result = p.search(message.content)

                if result:
                    try:
                        reason = "打出貢丸相關詞彙"
                        #await message.delete(reason=reason)
                        last = timedelta(seconds=60)
                        await message.author.timeout_for(duration=last,reason=reason)

                        embed = BotEmbed.simple_warn_sheet(message.author, self.bot.user, last=last, reason=reason)
                        await message.channel.send(f"{message.author.mention} 貢丸很危險 不要打貢丸知道嗎", embed=embed)
                        dbuser = sclient.sqldb.get_dcuser(message.author.id)
                        if dbuser.meatball_times is None:
                            dbuser.meatball_times = 1
                        else:
                            dbuser.meatball_times += 1
                        sclient.sqldb.merge(dbuser)
                    except Exception as e:
                        log.error(e)

                # 洗頻防制
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

            # 跨群聊天Ver.1.0
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

    # @commands.Cog.listener("on_message")
    # async def ai_trigger(self, message: discord.Message):
    #     #ai chat
    #     if message.guild and message.content and message.guild.id in ai_access_guilds and (len(message.content) > 1 or message.attachments) and message.content.startswith(".") and not message.content.startswith(".", 1, 2):
    #         async with message.channel.typing():
    #             image_bytes = None
    #             file = None
    #             if message.attachments:
    #                 att = message.attachments[0]
    #                 if att.content_type.startswith("image"):
    #                     image_bytes = await att.read()
    #                 elif att.content_type == "application/pdf":
    #                     file = sclient.starai.get_or_set_file(att.filename, await att.read())

    #         text = sclient.starai.generate_response(f"{Jsondb.get_member_name(message.author.id) or message.author.name}：{message.content[1:]}", image_bytes, file)
    #         if text:
    #             await message.reply(text,mention_author=False)
    #         else:
    #             await message.add_reaction('❌')

    @commands.Cog.listener("on_message")
    async def agent_trigger(self, message: discord.Message):
        #AI agent
        if not (
            message.guild
            and message.content
            and message.guild.id in ai_access_guilds
            and len(message.content) > 1
            and message.content.startswith(".")
            and not message.content.startswith(".", 1, 2)
        ):
            return

        cuser = sclient.sqldb.get_cloud_user(message.author.id)
        if not cuser or cuser.privilege_level < PrivilegeLevel.Level3:
            return

        async with message.channel.typing():
            global agent_history
            history = agent_history.get(message.author.id, [])
            deps = MyDeps(discord_id=message.author.id, member=message.author, guild=message.guild)

            resp = await agent.run(message.content[1:], message_history=history, deps=deps)
            if resp.output:
                agent_history[message.author.id] = list(resp.all_messages())
                await message.reply(resp.output, mention_author=False)
            else:
                await message.add_reaction("❌")

    @commands.Cog.listener("on_message")
    async def keyword_trigger(self, message: discord.Message):
        #關鍵字觸發
        if message.content.startswith("!") and message.author != self.bot.user:
            word = message.content.lstrip("!")
            if word == "azusa":
                bot_user = self.bot.get_user(1203368856647630878)
                assert bot_user
                embed = BotEmbed.user(
                    user=bot_user,
                    description=f"你好~我是假裝成星羽的Azusa，是一個discord機器人喔~\n你不可以輸入 </help:1067700245015834638> 來查看所有指令的用法\n\n希望我能在discord上幫助到你喔~\n有任何建議與需求不可以使用 </feedback:1067700244848058386> 指令\n\n支援伺服器：https://discord.gg/ye5yrZhYGF",
                )
                embed.set_footer(text="此機器人由 XX12 負責搞事")
                await message.reply(embed=embed)
            # elif word in keywords:
            #     await message.reply(keywords[word])

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

    @commands.Cog.listener("on_voice_state_update")
    async def dynamic_room_trigger(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # 動態語音
        if after.channel and (lobby_data := sclient.sqldb.cache.dynamic_voice_lobby.get(after.channel.id)):
            # 新增
            guild = after.channel.guild
            category = after.channel.category
            me = after.channel.guild.me
            # permission = discord.Permissions.advanced()
            # permission.manage_channels = True
            # overwrites = discord.PermissionOverwrite({user:permission})

            overwrites = {
                target: perms
                for target, perms in after.channel.overwrites.items()
                if (isinstance(target, discord.Member) and me.top_role > target.top_role) or (isinstance(target, discord.Role) and me.top_role > target)
            }
            if me.top_role > member.top_role:
                if member in overwrites:
                    # *注意成員位階比較高的情況
                    overwrites[member].manage_channels = True
                    overwrites[member].manage_roles = True
                    overwrites[member].view_channel = True
                else:
                    overwrites[member] = discord.PermissionOverwrite(manage_channels=True, manage_roles=True, view_channel=True)

            if me in overwrites:
                overwrites[me].manage_channels = True
                overwrites[me].manage_roles = True
                overwrites[me].view_channel = True
                overwrites[me].send_messages = True
            else:
                overwrites[me] = discord.PermissionOverwrite(manage_channels=True, manage_roles=True, view_channel=True, send_messages=True)

            channel_name = lobby_data.default_room_name.replace("{member}", member.name) if lobby_data.default_room_name is not None else f"{member.name}的頻道"
            try:
                new_channel = await guild.create_voice_channel(name=channel_name, reason="動態語音：新增", category=category, overwrites=overwrites)
            except discord.errors.Forbidden as e:
                try:
                    for overwrite in overwrites.values():
                        overwrite.manage_roles = None

                    new_channel = await guild.create_voice_channel(name=channel_name, reason="動態語音：新增", category=category, overwrites=overwrites)
                    log.debug("Created dynamic voice channel %s without manage_roles permission in %s", new_channel.id, guild.id)
                except discord.errors.Forbidden as e:
                    await after.channel.send(f"{member.mention} 我無法創建動態語音頻道，請檢查我的權限", delete_after=10)
                    log.debug("Failed to create dynamic voice channel %s in %s", new_channel.id, guild.id)
                    return
            sclient.sqldb.add_dynamic_voice(new_channel.id, member.id, guild.id)
            try:
                await member.move_to(new_channel)
            except discord.errors.HTTPException:
                await after.channel.send(f"{member.mention} 我無法把你移動至 {new_channel.mention}", delete_after=10)
                log.debug("Failed to move member %s to dynamic voice channel %s in %s", member.id, new_channel.id, guild.id)

            await asyncio.sleep(2)
            # 檢查使用者是否進入
            if self.bot.get_channel(new_channel.id) and len(new_channel.members) == 0:
                try:
                    await new_channel.delete(reason="動態語音：移除")
                    sclient.sqldb.remove_dynamic_voice(new_channel.id)
                except discord.errors.NotFound:
                    log.warning(f"動態語音頻道 {new_channel.id} 已經不存在")
                except discord.errors.Forbidden:
                    log.warning(f"無法刪除動態語音頻道 {new_channel.id}")
            return

        # 移除
        elif before.channel and not before.channel.members and sclient.sqldb.getif_dynamic_voice_room(before.channel.id):
            try:
                await before.channel.delete(reason="動態語音：移除")
                sclient.sqldb.remove_dynamic_voice(before.channel.id)
            except discord.errors.Forbidden:
                await before.channel.send(f"{member.mention} 我無法刪除動態語音頻道", delete_after=5)
                return

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if debug_mode:
            return

        guildid = get_guildid(before, after)

        # 語音進出紀錄
        if voice_updata:
            voice_log_data = sclient.sqldb.cache.voice_log.get(guildid)
            if voice_log_data is not None:
                NowTime = datetime.now()
                before_text = ""
                after_text = ""
                if before.channel:
                    before_text = (
                        before.channel.mention if not sclient.sqldb.getif_dynamic_voice_room(before.channel.id) else before.channel.name + " (動態語音)"
                    )
                if after.channel:
                    after_text = after.channel.mention if not sclient.sqldb.getif_dynamic_voice_room(after.channel.id) else after.channel.name + " (動態語音)"

                if not before.channel:
                    embed = discord.Embed(description=f"{member.mention} 進入語音", color=0x4AA0B5, timestamp=NowTime)
                    embed.add_field(name="頻道", value=f"{after_text}", inline=False)
                elif not after.channel:
                    embed = discord.Embed(description=f"{member.mention} 離開語音", color=0x4AA0B5, timestamp=NowTime)
                    embed.add_field(name="頻道", value=f"{before_text}", inline=False)
                elif before.channel != after.channel:
                    embed = discord.Embed(description=f"{member.mention} 更換語音", color=0x4AA0B5, timestamp=NowTime)
                    embed.add_field(name="頻道", value=f"{before_text}->{after_text}", inline=False)
                else:
                    return

                username = member.name if member.discriminator == "0" else member
                embed.set_author(name=username,icon_url=member.display_avatar.url)
                embed.set_footer(text=member.guild.name)

                await self.bot.get_channel(voice_log_data[0]).send(embed=embed)

        # 舞台發言
        # if check_event_stage(before) or check_event_stage(after):
        #     kp_user = self.bot.get_guild(613747262291443742).get_member(713748326377455676)
        #     #調查員、特許證舞台發言
        #     if after.suppress and after.channel and ( user.get_role(1126820808761819197) or (user.get_role(1130849778264195104) and not kp_user in after.channel.members) ):
        #         await user.request_to_speak()
        #         await asyncio.sleep(0.5)

        #     if user == kp_user and before.channel != after.channel:
        #         if after.channel:
        #             for member in after.channel.members:
        #                 if not member.voice.suppress and not member.get_role(1126820808761819197):
        #                     await member.edit(suppress=True)
        #                     await asyncio.sleep(0.5)

        #         if before.channel:
        #             for member in before.channel.members:
        #                 if member.voice.suppress and member.get_role(1126820808761819197):
        #                     await member.request_to_speak()
        #                     await asyncio.sleep(0.5)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if debug_mode:
            return

        #離開通知
        guildid = member.guild.id
        dbdata = sclient.sqldb.get_notify_channel(guildid, NotifyChannelType.MemberLeave)

        if dbdata:
            username = member.name if member.discriminator == "0" else f"{member.name}#{member.discriminator}"
            text = (
                dbdata.message.replace("{member}", member.mention).replace("{guild}", member.guild.name)
                if dbdata.message
                else f"{member.mention} ({username}) 離開了我們"
            )
            await self.bot.get_channel(dbdata.channel_id).send(text)

        # 離開日誌
        notify_data = sclient.sqldb.get_notify_channel(guildid, NotifyChannelType.LeaveLog)
        if notify_data:
            log_channel_id = notify_data.channel_id
            channel = self.bot.get_channel(log_channel_id)
            description = f"{member.mention} 離開了伺服器"
            roles_mention = [r.mention for r in member.roles if not r.is_default()]
            if roles_mention:
                description += f"\n身分組：{', '.join(roles_mention)}"
            if member.joined_at:
                description += f"\n加入時長：{timedelta(seconds=int((datetime.now(tz=tz) - member.joined_at).total_seconds()))}"
            embed = BotEmbed.general(name=member.name, title="成員離開", description=description, icon_url=member.display_avatar.url)
            embed.timestamp = datetime.now(tz=tz)
            embed.set_footer(text=f"ID: {member.id}")
            await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_join(self, member:discord.Member):
        if debug_mode:
            return

        # 加入通知
        guildid = member.guild.id
        dbdata = sclient.sqldb.get_notify_channel(guildid, NotifyChannelType.MemberJoin)

        if dbdata:
            username = member.name if member.discriminator == "0" else f"{member.name}#{member.discriminator}"
            text = (
                dbdata.message.replace("{member}", member.mention).replace("{guild}", member.guild.name)
                if dbdata.message
                else f"{member.mention} ({username}) 加入了我們"
            )

            channel = self.bot.get_channel(dbdata.channel_id)
            if channel:
                await channel.send(text)
            else:
                log.warning(f"Member join channel: {dbdata.channel_id} not found")

        # 加入日誌 / 警告系統：管理員通知
        notify_data = sclient.sqldb.get_notify_channel(guildid, NotifyChannelType.JoinLog)
        if notify_data:
            log_channel_id = notify_data.channel_id
            dbdata = sclient.sqldb.get_warnings_count(member.id)
            description = f"{member.mention} ({member.id})\n共有 {dbdata} 筆跨群紀錄" if dbdata else f"{member.mention} 加入了伺服器"
            description += f"\n第 {member.guild.member_count} 位成員"

            channel = self.bot.get_channel(log_channel_id)
            embed = BotEmbed.general(name=member.name, title="成員加入", description=description, icon_url=member.display_avatar.url)
            embed.timestamp = datetime.now(tz=tz)
            embed.set_footer(text=f"ID: {member.id}")
            if channel:
                await channel.send(embed=embed)
            else:
                log.warning(f"Member join log channel: {log_channel_id} not found")

        # 快樂營戶籍註冊
        if guildid == happycamp_guild[0]:
            earlest_guildid = check_registration(member)
            if earlest_guildid and earlest_guildid != happycamp_guild[0]:
                from starlib.database.postgresql.models import DiscordUser

                dbdata = sclient.sqldb.get_registration_by_guildid(earlest_guildid)
                user = DiscordUser(discord_id=member.id, registrations_id=dbdata.registrations_id)
                sclient.sqldb.merge(user)
                await member.add_roles(member.guild.get_role(dbdata.role_id), reason="加入的最早伺服器")


    @commands.Cog.listener()
    async def on_guild_join(self, guild:discord.Guild):
        report_channel = self.bot.get_channel(Jsondb.config.report_channel)
        await report_channel.send(f"公會異動：我加入了 {guild.name} ({guild.id})")

    @commands.Cog.listener()
    async def on_guild_remove(self, guild:discord.Guild):
        report_channel = self.bot.get_channel(Jsondb.config.report_channel)
        await report_channel.send(f"公會異動：我離開了 {guild.name} ({guild.id})")

    @commands.Cog.listener()
    async def on_member_update(self,before:discord.Member, after:discord.Member):
        guildid = after.guild.id
        member = after
        if guildid in happycamp_guild and before.nick != after.nick:
            p2 = re.compile(r"冠宇")
            nick = after.nick

            if nick and p2.search(nick):
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

    @commands.Cog.listener()
    async def on_audit_log_entry(self, entry: discord.AuditLogEntry):
        if entry.guild.id == happycamp_guild[0] and entry.action == discord.AuditLogAction.member_update and entry.user != self.bot.user:
            member: discord.Member = entry.target
            if member.timed_out and entry.user != member:
                await asyncio.sleep(10)
                await member.remove_timeout()


def setup(bot):
    bot.add_cog(event(bot))
