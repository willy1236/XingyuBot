import io
from datetime import timedelta

import discord
from discord.commands import SlashCommandGroup
from discord.ext import commands
from discord.utils import format_dt

from starlib import BotEmbed, ChoiceList, Jsondb, sclient
from starlib import auto_timeout as auto_timeout_module
from starlib.database import NotifyChannelType, ReactionRoleMessage, ReactionRoleOption, TicketChannelLobby, WarningType
from starlib.database.postgresql.models import AUTO_TIMEOUT_DEFAULT_SECONDS, AUTO_TIMEOUT_DEFAULT_TIMES
from starlib.dynamic_voice import lobby_permission_issues
from starlib.instance import debug_guilds
from starlib.message_content import from_json, from_message, to_json
from starlib.moderation import PunishResult, announcement, audit_reason, delete_recent_messages, punish
from starlib.utils import format_seconds, nowtz, time_to_datetime

from ..extension import Cog_Extension
from ..uiElement.modal import RuleMessageModal
from ..uiElement.view import ReactionRoleView, TicketLobbyView

set_option = ChoiceList.set("channel_set_option")
ban_delete_message_seconds = [
    discord.OptionChoice(name="不要刪除訊息", value=0),
    discord.OptionChoice(name="1小時", value=3600),
    discord.OptionChoice(name="6小時", value=21600),
    discord.OptionChoice(name="12小時", value=43200),
    discord.OptionChoice(name="1天", value=86400),
    discord.OptionChoice(name="3天", value=259200),
    discord.OptionChoice(name="7天", value=604800),
]


async def _punish_command(
    ctx: discord.ApplicationContext,
    kind: WarningType,
    user: discord.Member,
    reason: str | None,
    add_record: bool,
    *,
    duration: timedelta | None = None,
    delete_message_seconds: int | None = None,
) -> PunishResult:
    """指令懲處的共用入口：一般情況走 punish；punish 會拒絕但現行指令允許的對象（機器人、執行者自己）走保留路徑，行為維持現況，機器人不寫紀錄。"""
    if not (user.bot or user.id == ctx.author.id):
        return await punish(
            ctx.guild,
            kind,
            user,
            ctx.author,
            reason,
            cross_guild=add_record,
            duration=duration,
            delete_message_seconds=delete_message_seconds,
            via_dashboard=False,
        )

    result = PunishResult(ok=False)
    audit = audit_reason(ctx.author, reason, False)
    try:
        if kind == WarningType.Timeout:
            await user.timeout_for(duration, reason=audit)
            if delete_message_seconds:
                result.deleted_summary = await delete_recent_messages(ctx.guild, user.id, delete_message_seconds)
        elif kind == WarningType.Kick:
            await user.kick(reason=audit)
        else:
            await user.ban(reason=audit, delete_message_seconds=delete_message_seconds or 0)
    except discord.HTTPException as e:
        result.error = f"Discord 錯誤：{e}"
        return result
    result.ok = True
    if not user.bot:
        result.warning_id = sclient.sqldb.add_warning(user.id, kind, ctx.author.id, ctx.guild.id, nowtz(), reason, duration, guild_only=not add_record)
    return result


async def _respond_kick_ban(ctx: discord.ApplicationContext, result: PunishResult, user: discord.Member, title_suffix: str, reason: str | None):
    """/kick、/ban 的回覆：有紀錄時用統一公告格式，沒有紀錄（對象是機器人）時用簡單 embed。"""
    if not result.ok:
        await ctx.respond(f"錯誤：{result.error}")
    elif result.warning_id is not None or not user.bot:
        payload = announcement(result, user, ctx.author)
        if result.error:
            payload["embed"].add_field(name="注意", value=result.error, inline=False)
        await ctx.respond(**payload)
    else:
        embed = BotEmbed.general(f"{user.name} {title_suffix}", user.display_avatar.url, description=f"{user.mention}：{reason}")
        embed.add_field(name="執行人員", value=ctx.author.mention)
        embed.timestamp = nowtz()
        await ctx.respond(embed=embed)


class moderation(Cog_Extension):
    warning_cmd = SlashCommandGroup("warning", "警告相關指令", name_localizations=ChoiceList.name("warning"))
    channel_cmd = SlashCommandGroup("channel", "自動通知相關指令", name_localizations=ChoiceList.name("channel"))
    reactrole_cmd = SlashCommandGroup("reactrole", "反應身分組相關指令", name_localizations=ChoiceList.name("reactrole"))
    ticket_cmd = SlashCommandGroup("ticket", "私人頻道相關指令", name_localizations=ChoiceList.name("ticket"))
    server_cmd = SlashCommandGroup("server", "伺服器設定相關指令", name_localizations=ChoiceList.name("server"))

    @commands.slash_command(description="清理大量訊息", name_localizations=ChoiceList.name("clean"))
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_guild_permissions(manage_messages=True)
    @commands.guild_only()
    async def clean(
        self,
        ctx: discord.ApplicationContext,
        num: discord.Option(int, name="數量", description="要清理的訊息數，與訊息id擇一提供", required=False),
        message_id: discord.Option(
            str,
            name="訊息id",
            description="如果提供，將刪除比此訊息更新的所有訊息（該訊息本身不會被刪）",
            required=False,
        ),
    ):
        await ctx.defer()
        if message_id:
            message = await ctx.channel.fetch_message(int(message_id))
            if message:
                time = message.created_at
                await ctx.respond(content="開始清除")
                await ctx.channel.purge(after=time)
            else:
                await ctx.respond(content="沒有找到此訊息", ephemeral=True)

        elif num:
            await ctx.respond(content=f"開始清除{num}則訊息")
            await ctx.channel.purge(limit=num)
        else:
            await ctx.respond(content="沒有提供任何資訊，所以沒有清除任何內容", delete_after=5)

    @channel_cmd.command(description="設定通知頻道，讓機器人發送通知", name_localizations=ChoiceList.name("channel_set"))
    @commands.has_permissions(manage_channels=True)
    @commands.guild_only()
    async def set(
        self,
        ctx: discord.ApplicationContext,
        notify_type: discord.Option(int, name="通知類型", description="要接收的通知類型", required=True, choices=set_option),
        channel: discord.Option(discord.abc.GuildChannel, name="頻道", description="要接收通知的頻道，留空以移除通知", default=None),
        role: discord.Option(
            discord.Role,
            required=False,
            name="身分組",
            description="發送通知時tag的身分組，定時通知與部分通知不會tag故不一定需要設定",
            default=None,
        ),
        msg: discord.Option(str, name="通知文字", description="發送通知時的自訂文字，目前僅部分通知會使用到", default=None),
    ):
        guildid = ctx.guild.id
        notify_type = NotifyChannelType(notify_type)

        if channel:
            roleid = role.id if role else None
            sclient.sqldb.add_notify_channel(guildid, notify_type, channel.id, roleid, msg)
            await ctx.respond(f"設定完成，已將 {Jsondb.get_tw(notify_type, 'channel_set_option')} 頻道設定在 {channel.mention}")
            await ctx.send(
                embed=BotEmbed.simple("溫馨提醒", "若為定時通知，請將機器人的訊息保持在此頻道的最新訊息，以免機器人找不到訊息而重複發送"),
                delete_after=10,
            )
            if not channel.can_send():
                await ctx.send(embed=BotEmbed.simple("溫馨提醒", f"我無法在{channel.mention}中發送訊息，請確認我有足夠的權限"))
        else:
            sclient.sqldb.remove_notify_channel(guildid, notify_type)
            await ctx.respond(f"設定完成，已移除 {Jsondb.get_tw(notify_type, 'channel_set_option')} 頻道")

    @channel_cmd.command(
        name="voice",
        description="設定動態語音大廳頻道，當有人進入時會自動建立新的語音頻道，並在沒人時自動刪除",
        name_localizations=ChoiceList.name("channel_voice"),
    )
    @commands.has_permissions(manage_channels=True)
    @commands.guild_only()
    async def voice(
        self,
        ctx: discord.ApplicationContext,
        channel: discord.Option(discord.VoiceChannel, name="動態語音大廳頻道", description="留空以移除設定", default=None),
        default_room_name: discord.Option(
            str,
            name="預設房間名稱",
            description="當建立新語音頻道時的預設名稱，使用 {member} 代表建立者名稱",
            default=None,
        ),
    ):
        if channel:
            assert isinstance(channel, discord.VoiceChannel), "頻道必須是語音頻道"
            sclient.sqldb.add_dynamic_voice_lobby(ctx.guild.id, channel.id, default_room_name)
            await ctx.respond(
                f"設定完成，已將 {channel.mention} 設定為動態語音大廳頻道\n記得將我的身分組位階調整到比其他使用者高，否則建立頻道後使用者會得不到權限\n並且可以設定大廳頻道的權限，讓動態語音頻道有預設的權限",
            )
            texts = [f"我缺少「{i.permission}」權限，{i.consequence}" for i in lobby_permission_issues(channel)]

            if texts:
                await ctx.send(embed=BotEmbed.simple("溫馨提醒", "\n".join(texts)), delete_after=5 * len(texts))
        else:
            sclient.sqldb.remove_dynamic_voice_lobby(ctx.guild.id)
            await ctx.respond("設定完成，已移除 動態語音大廳 頻道")

    @channel_cmd.command(name="list", description="查看所有通知設定的頻道", name_localizations=ChoiceList.name("channel_list"))
    @commands.has_permissions(manage_channels=True)
    @commands.guild_only()
    async def channel_list(self, ctx: discord.ApplicationContext):
        dbdata = sclient.sqldb.get_notify_channel_all(ctx.guild.id)
        embed = BotEmbed.general("通知頻道", ctx.guild.icon.url if ctx.guild.icon else None)
        for data in dbdata:
            notify_type = data.notify_type
            channel_id = data.channel_id
            role_id = data.role_id

            channel = self.bot.get_channel(channel_id)
            role = ctx.guild.get_role(role_id) if role_id else None

            text = "找不到頻道"
            if channel:
                text = channel.mention
                if role:
                    text += f" {role.mention}"
            embed.add_field(name=Jsondb.get_tw(notify_type, "channel_set_option"), value=text)
        await ctx.respond(embed=embed)

    @warning_cmd.command(
        name="add",
        description="給予使用者警告，此警告可選擇連動至其他群組",
        name_localizations=ChoiceList.name("warning_add"),
    )
    @commands.has_guild_permissions(manage_messages=True)
    @commands.guild_only()
    async def warning_add(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Option(discord.User, name="用戶", description="要給予警告的用戶", required=True),
        reason: discord.Option(str, name="原因", description="限100字內"),
        add_record: discord.Option(bool, name="是否要將此紀錄存入警告系統", description="將紀錄存入警告系統供其他群組檢視", default=False),
    ):
        is_owner = await self.bot.is_owner(ctx.author)
        if (ctx.author == user or user not in ctx.guild.members) and not is_owner:
            await ctx.respond("只能警告在伺服器內的成員")
            return
        if user.bot:
            await ctx.respond("不能警告機器人")
            return

        time = nowtz()
        record_error = None
        if user.id == ctx.author.id:
            # 只有 owner 能走到這裡；punish 不允許對自己執行，沿用現行寫法
            warning_id = sclient.sqldb.add_warning(user.id, WarningType.Warning, ctx.author.id, ctx.guild.id, time, reason, None, not add_record)
        else:
            result = await punish(ctx.guild, WarningType.Warning, user, ctx.author, reason, cross_guild=add_record, via_dashboard=False)
            if not result.ok:
                await ctx.respond(result.error)
                return
            warning_id = result.warning_id
            record_error = result.error
        embed = BotEmbed.general(f"{user.name} 已被警告", user.display_avatar.url, description=f"{user.mention}：{reason}")
        embed.add_field(name="執行人員", value=ctx.author.mention)
        embed.add_field(name="存入跨群警告系統", value=add_record)
        embed.timestamp = time
        if warning_id is not None:
            embed.set_footer(text=f"編號 {warning_id}")
        if record_error:
            embed.add_field(name="注意", value=record_error, inline=False)

        await ctx.respond(user.mention, embed=embed, allowed_mentions=discord.AllowedMentions(users=True))

    @warning_cmd.command(name="list", description="獲取使用者的所有警告", name_localizations=ChoiceList.name("warning_list"))
    @commands.guild_only()
    async def list(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Option(discord.User, name="使用者", description="要查詢的使用者", required=True),
        guild_only: discord.Option(
            bool,
            name="查詢是否包含伺服器內警告",
            description="若未存入警告系統的警告為伺服器內警告，預設為True",
            default=True,
        ),
    ):
        dbdata = sclient.sqldb.get_warnings(user.id, ctx.guild.id if guild_only else None)
        await ctx.respond(embed=dbdata.display(self.bot, user))

    @warning_cmd.command(name="get", description="查詢指定警告的資訊", name_localizations=ChoiceList.name("warning_get"))
    @commands.guild_only()
    async def get(
        self,
        ctx: discord.ApplicationContext,
        warning_id: discord.Option(str, name="警告編號", description="要查詢的警告", required=True),
    ):
        sheet = sclient.sqldb.get_warning(int(warning_id))
        if sheet and (ctx.guild.id == sheet.create_guild or ctx.guild.id in debug_guilds or ctx.guild.get_member(sheet.discord_id)):
            await ctx.respond(embed=sheet.embed(self.bot))
        else:
            await ctx.respond("查無此警告單")

    @warning_cmd.command(name="remove", description="移除使用的指定警告", name_localizations=ChoiceList.name("warning_remove"))
    @commands.check_any(
        commands.has_guild_permissions(kick_members=True),
        commands.has_guild_permissions(ban_members=True),
        commands.has_guild_permissions(manage_messages=True),
    )
    @commands.guild_only()
    async def warning_remove(
        self,
        ctx: discord.ApplicationContext,
        warning_id: discord.Option(str, name="警告編號", description="要移除的警告", required=True),
    ):
        dbdata = sclient.sqldb.get_warning(int(warning_id))
        is_owner = await self.bot.is_owner(ctx.author)
        if dbdata:
            guild = self.bot.get_guild(dbdata.create_guild)
            if guild != ctx.guild and not is_owner:
                await ctx.respond("不能移除非此伺服器發出的警告")
                return
            sclient.sqldb.remove_warning(int(warning_id))
            await ctx.respond(f"已移除編號：{warning_id}的警告")
        else:
            await ctx.respond("查無此警告單")

    @commands.slash_command(description="禁言使用者", name_localizations=ChoiceList.name("timeout"))
    @commands.has_guild_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    @commands.guild_only()
    async def timeout(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Option(discord.Member, name="用戶", description="要禁言的使用者", required=True),
        time_last_str: discord.Option(str, name="時長", description="格式為30s、1h20m等，支援天(d)、小時(h)、分鐘(m)、秒(s)", required=True),
        reason: discord.Option(str, name="原因", description="限100字內", default="已禁言"),
        add_record: discord.Option(bool, name="是否要將此紀錄存入警告系統", description="將紀錄存入警告系統供其他群組檢視", default=False),
        delete_message_seconds: discord.Option(
            int,
            name="刪除最近的訊息",
            description="若提供，將刪除此使用者在整個伺服器指定秒數內的訊息",
            default=None,
            min_value=0,
            max_value=604800,
        ),
    ):
        await ctx.defer()
        time_last = time_to_datetime(time_last_str)
        if not time_last or time_last > timedelta(days=7):
            await ctx.respond("錯誤：時間格式錯誤（不得超過7天）")
            return

        result = await _punish_command(
            ctx,
            WarningType.Timeout,
            user,
            reason,
            add_record,
            duration=time_last,
            delete_message_seconds=delete_message_seconds,
        )
        if not result.ok:
            await ctx.respond(f"錯誤：{result.error}")
            return

        create_time = nowtz()
        embed = BotEmbed.general(f"{user.name} 已被禁言", user.display_avatar.url, description=f"{user.mention}：{reason}")
        embed.add_field(name="執行人員", value=ctx.author.mention)
        embed.add_field(name="結束時間", value=f"{format_dt(create_time + time_last, style='T')}（{time_last}）")
        if result.deleted_summary:
            embed.add_field(name="訊息刪除", value=result.deleted_summary, inline=False)
        embed.timestamp = create_time
        if result.warning_id is not None:
            embed.set_footer(text=f"編號 {result.warning_id}")
        if result.error:
            embed.add_field(name="注意", value=result.error, inline=False)
        await ctx.respond(user.mention, embed=embed, allowed_mentions=discord.AllowedMentions(users=True))

    @commands.slash_command(description="踢出用戶", name_localizations=ChoiceList.name("kick"))
    @commands.has_guild_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    @commands.guild_only()
    async def kick(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Option(discord.Member, name="用戶", description="要踢出的用戶", required=True),
        reason: discord.Option(str, name="原因", description="限100字內", required=False),
        add_record: discord.Option(bool, name="是否要將此紀錄存入警告系統", description="將紀錄存入警告系統供其他群組檢視", default=False),
    ):
        await ctx.defer()
        result = await _punish_command(ctx, WarningType.Kick, user, reason, add_record)
        await _respond_kick_ban(ctx, result, user, "已被踢出", reason)

    @commands.slash_command(description="停權用戶", name_localizations=ChoiceList.name("ban"))
    @commands.has_guild_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    @commands.guild_only()
    async def ban(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Option(discord.Member, name="用戶", description="要停權的用戶", required=True),
        reason: discord.Option(str, name="原因", description="限100字內", required=True),
        add_record: discord.Option(bool, name="是否要將此紀錄存入警告系統", description="將紀錄存入警告系統供其他群組檢視", default=False),
        delete_message_seconds: discord.Option(
            int,
            name="刪除最近的訊息",
            description="若提供，將刪除用戶指定秒數內的所有訊息",
            default=None,
            min_value=0,
            max_value=604800,
            choices=ban_delete_message_seconds,
        ),
    ):
        await ctx.defer()
        assert isinstance(user, discord.Member), "user must be a discord.Member instance"
        result = await _punish_command(ctx, WarningType.Ban, user, reason, add_record, delete_message_seconds=delete_message_seconds)
        await _respond_kick_ban(ctx, result, user, "已被停權", reason)

    @staticmethod
    def _store_content_after_edit(react_msg: ReactionRoleMessage, edited: discord.Message, content: str) -> None:
        """`/reactrole editmessage` 改完文字後，同步 bot 記住的訊息內容（重新發送用）。"""
        stored = None
        if react_msg.content_json:
            try:
                stored = from_json(react_msg.content_json)
            except ValueError:  # pydantic 的 ValidationError 是 ValueError 的子類別
                stored = None
        if stored is not None:
            stored.content = content
        else:
            stored, _ = from_message(edited)
        if stored is not None:
            sclient.sqldb.merge(
                ReactionRoleMessage(
                    guild_id=react_msg.guild_id, channel_id=react_msg.channel_id, message_id=react_msg.message_id, content_json=to_json(stored)
                )
            )

    @reactrole_cmd.command(description="編輯反應身分組訊息的文字", name_localizations=ChoiceList.name("reactrole_editmessage"))
    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    async def editmessage(
        self,
        ctx: discord.ApplicationContext,
        message_id: discord.Option(str, name="訊息id", description="要編輯的訊息id", required=True),
        content: discord.Option(str, name="訊息", description="新的訊息文字", required=True),
    ):
        await ctx.defer()
        message = self.bot.get_message(int(message_id)) or await ctx.channel.fetch_message(int(message_id))
        if not message:
            await ctx.respond("找不到此訊息，請在該訊息的頻道進行設定", ephemeral=True)
            return

        react_msg = sclient.sqldb.get_reaction_role_message(message.id)
        if not react_msg:
            await ctx.respond("請先新增反應身分組", ephemeral=True)
            return

        edited = await message.edit(content=content)
        self._store_content_after_edit(react_msg, edited, content)
        await ctx.respond("編輯完成", ephemeral=True)

    @reactrole_cmd.command(description="新增反應身分組", name_localizations=ChoiceList.name("reactrole_add"))
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def add(
        self,
        ctx: discord.ApplicationContext,
        role: discord.Option(discord.Role, name="身分組", description="要設定的身分組", required=True),
        title: discord.Option(str, name="標題", description="要設定的標題，只能展示出純文字的效果", required=True),
        emoji: discord.Option(str, name="表情符號", description="要設定的表情符號", required=False),
        style: discord.Option(discord.ButtonStyle, name="樣式", description="要設定的樣式", required=False),
        message_id: discord.Option(str, name="訊息id", description="要設定的訊息id，若無則由機器人創建", required=False),
        text: discord.Option(str, name="訊息文字", description="機器人發送新訊息時的文字", default="請依自身喜好點選身分組"),
    ):
        # TODO: 設定不同頻道訊息
        if role.is_default() or role.managed:
            await ctx.respond("無法設定 @everyone 或由整合服務管理的身分組", ephemeral=True)
            return
        if role >= ctx.guild.me.top_role:
            await ctx.respond("此身分組不低於我的最高身分組，我無法發放", ephemeral=True)
            return
        if ctx.author.id != ctx.guild.owner_id and role >= ctx.author.top_role:
            await ctx.respond("只能設定低於你最高身分組的身分組", ephemeral=True)
            return

        await ctx.defer()
        if message_id:
            message: discord.Message | None = self.bot.get_message(int(message_id)) or await ctx.channel.fetch_message(int(message_id))
            if not message:
                await ctx.respond("找不到此訊息，請在該訊息的頻道進行設定", ephemeral=True)
                return
            elif message.author != ctx.bot.user:
                await ctx.respond("此訊息非我所發送", ephemeral=True)
                return
        else:
            message = await ctx.channel.send(text)

        react_msg = sclient.sqldb.get_reaction_role_message(message.id)
        if not react_msg or react_msg.content_json is None:
            content, _ = from_message(message)
            sclient.sqldb.merge(
                ReactionRoleMessage(
                    guild_id=message.guild.id,
                    channel_id=message.channel.id,
                    message_id=message.id,
                    content_json=to_json(content) if content else None,
                )
            )

        existing = {r.role_id: r for r in sclient.sqldb.get_reaction_roles_by_message(message.id)}
        if role.id in existing:
            position = existing[role.id].position
        else:
            position = max((r.position for r in existing.values()), default=-1) + 1
        sclient.sqldb.merge(
            ReactionRoleOption(message_id=message.id, role_id=role.id, title=title, description=None, emoji=emoji, style=style, position=position)
        )
        react_roles = sclient.sqldb.get_reaction_roles_by_message(message.id)
        await message.edit(view=ReactionRoleView(message.id, react_roles))

        await ctx.respond(f"已新增 {title} 給 {role.mention}", ephemeral=True)

    @reactrole_cmd.command(description="移除反應身分組", name_localizations=ChoiceList.name("reactrole_remove"))
    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    async def remove(
        self,
        ctx: discord.ApplicationContext,
        message_id: discord.Option(str, name="訊息id", description="要移除的訊息id", required=True),
        role: discord.Option(discord.Role, name="身分組", description="要移除的身分組", required=True),
    ):
        await ctx.defer()
        message = self.bot.get_message(int(message_id)) or await ctx.channel.fetch_message(int(message_id))
        if not message:
            await ctx.respond("找不到此訊息，請在該訊息的頻道進行設定", ephemeral=True)
            return
        elif message.author != ctx.bot.user:
            await ctx.respond("此訊息非我所發送", ephemeral=True)
            return

        sclient.sqldb.delete_reaction_role(message.id, role.id)
        react_roles = sclient.sqldb.get_reaction_roles_by_message(message.id)
        if not react_roles:
            sclient.sqldb.delete_reaction_role_message(message.id)
            await message.edit(view=None)
        else:
            await message.edit(view=ReactionRoleView(message.id, react_roles))

        await ctx.respond(f"已移除 {role.mention}", ephemeral=True)

    @commands.slash_command(description="創建規則訊息（開發中）")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def rule_message(
        self,
        ctx: discord.ApplicationContext,
        channel: discord.Option(discord.TextChannel, name="頻道", description="要創建規則的頻道", required=True),
        attachment: discord.Option(
            discord.Attachment,
            name="圖片",
            description="若提供，則在規則前會先放置該圖片，可用於分隔區塊",
            required=False,
        ),
    ):
        modal = RuleMessageModal()
        await ctx.send_modal(modal)
        await modal.wait()
        if attachment:
            await channel.send(file=discord.File(io.BytesIO(await attachment.read()), filename=attachment.filename))
        embed = BotEmbed.simple(title=modal.children[0].value, description=modal.children[1].value)
        await channel.send(embed=embed)
        await ctx.respond("規則創建完成", ephemeral=True)

    @ticket_cmd.command(name="setup", description="初始化私人頻道系統", name_localizations=ChoiceList.name("ticket_setup"))
    @commands.has_permissions(manage_channels=True)
    @commands.guild_only()
    async def ticket_setup(
        self,
        ctx: discord.ApplicationContext,
        category: discord.Option(discord.CategoryChannel, name="分類", description="要將私人頻道放置於哪個分類下", required=True),
        # role: discord.Option(discord.Role, name="管理身分組", description="擁有此身分組的使用者可以查看與管理所有私人頻道", required=True),
        # prefix: discord.Option(str, name="頻道前綴", description="私人頻道的名稱前綴，後方會自動加上流水號", default="ticket"),
        # max_channel: discord.Option(int, name="最大頻道數量", description="同時存在的私人頻道上限，超過後將無法再創建新的私人頻道", default=10, min_value=1),
    ):
        await ctx.defer()
        assert isinstance(category, discord.CategoryChannel)
        channel = await category.create_text_channel(name="開單頻道", reason="初始化私人頻道系統（測試版）")
        embed = BotEmbed.general(
            "私人頻道系統",
            self.bot.user.display_avatar.url if self.bot.user else None,
            description="點擊下方按鈕以建立私人頻道",
        )
        msg = await channel.send(embed=embed, view=TicketLobbyView(channel.id))
        sclient.sqldb.merge(
            TicketChannelLobby(
                channel_id=channel.id,
                category_id=category.id,
                guild_id=channel.guild.id,
                message_id=msg.id,
            )
        )
        await ctx.respond("私人頻道系統初始化完成", ephemeral=True)

    @server_cmd.command(name="setting", description="查看或修改伺服器設定，只填要改的項目；不填任何項目則顯示目前設定", name_localizations=ChoiceList.name("server_setting"))
    @commands.has_guild_permissions(manage_guild=True)
    @commands.guild_only()
    async def server_setting(
        self,
        ctx: discord.ApplicationContext,
        voice_time_counter: discord.Option(bool, name="語音時數統計", description="是否統計成員的語音時數", required=False),
        auto_timeout: discord.Option(bool, name="自動禁言", description="警告累計到指定次數時是否自動禁言", required=False),
        times: discord.Option(int, name="警告次數", description="累計幾次警告自動禁言（1～20）", required=False, min_value=1, max_value=20),
        duration: discord.Option(str, name="禁言時長", description="格式為30s、1h20m等，支援天(d)、小時(h)、分鐘(m)、秒(s)，1分鐘到7天", required=False),
    ):
        db = sclient.sqldb
        values: dict[str, bool | int] = {}
        if duration is not None:
            seconds = auto_timeout_module.parse_duration(duration)
            if seconds is None:
                await ctx.respond("錯誤：禁言時長格式錯誤，需為整分鐘、1 分鐘到 7 天，例如 30m、1h20m", ephemeral=True)
                return
            values["auto_timeout_seconds"] = seconds
        if voice_time_counter is not None:
            values["voice_time_counter"] = voice_time_counter
        if auto_timeout is not None:
            values["auto_timeout_enabled"] = auto_timeout
        if times is not None:
            values["timeout_after_warning_times"] = times

        if values:
            if auto_timeout:
                # 啟用時次數與時長還沒設定過就寫入預設值，之後在設定裡看到的就是實際生效的值
                row = db.get_guild_setting_fresh(ctx.guild.id)
                if (row is None or row.timeout_after_warning_times is None) and times is None:
                    values["timeout_after_warning_times"] = AUTO_TIMEOUT_DEFAULT_TIMES
                if (row is None or row.auto_timeout_seconds is None) and duration is None:
                    values["auto_timeout_seconds"] = AUTO_TIMEOUT_DEFAULT_SECONDS
            db.upsert_guild_setting(ctx.guild.id, values)
            db.refresh_voice_time_counter_cache()

        row = db.get_guild_setting_fresh(ctx.guild.id)
        auto = auto_timeout_module.effective_setting(row)
        embed = BotEmbed.general("伺服器設定" if not values else "伺服器設定已更新", ctx.guild.icon.url if ctx.guild.icon else None)
        embed.add_field(name="語音時數統計", value="開啟" if row is not None and row.voice_time_counter else "關閉")
        embed.add_field(
            name="自動禁言",
            value=f"警告累計 {auto.times} 次禁言 {format_seconds(auto.seconds)}" if auto.enabled else f"關閉（啟用時為累計 {auto.times} 次禁言 {format_seconds(auto.seconds)}）",
            inline=False,
        )
        issue = auto_timeout_module.moderate_members_issue(ctx.guild)
        if auto.enabled and issue:
            embed.add_field(name="注意", value=f"機器人缺少 {issue.permission}：{issue.consequence}", inline=False)
        await ctx.respond(embed=embed, ephemeral=True)


def setup(bot):
    auto_timeout_module.register()
    bot.add_cog(moderation(bot))
