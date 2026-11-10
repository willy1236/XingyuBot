"""
### 模組：懲處服務
警告、禁言、踢出、停權的執行、紀錄寫入、公告內容與稽核原因。
後台 API、指令與自動禁言走同一條路，行為保持一致。
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta

import discord

from starlib.database import WarningType
from starlib.pubsub import sclient
from starlib.utils import BotEmbed, nowtz

log = logging.getLogger(__name__)

MAX_TIMEOUT = timedelta(days=7)
MAX_AUDIT_REASON = 512
PURGE_LIMIT_PER_CHANNEL = 50

PunishKind = WarningType


@dataclass
class AutoTimeoutResult:
    """自動禁言的結果，由 B-02 的 hook 回傳。"""

    ok: bool
    duration: timedelta | None = None
    error: str | None = None


@dataclass
class PunishResult:
    ok: bool
    error: str | None = None
    warning_id: int | None = None
    already: bool = False
    deleted_summary: str | None = None
    auto_timeout: AutoTimeoutResult | None = None


AfterWarningHook = Callable[[discord.Guild, discord.User | discord.Member, int], Awaitable[AutoTimeoutResult | None]]

_after_warning: AfterWarningHook | None = None


def register_after_warning(fn: AfterWarningHook | None) -> None:
    """註冊警告寫入後的鉤子（只有一個，B-02 使用）。傳入 None 取消註冊。"""
    global _after_warning
    _after_warning = fn


def audit_reason(actor: discord.Member | discord.User, reason: str | None, via_dashboard: bool) -> str:
    """產生 Discord 稽核日誌的 reason，超過上限時截斷。"""
    text = reason or ""
    if via_dashboard:
        text = f"{actor.name} 透過後台：{text}"
    if len(text) > MAX_AUDIT_REASON:
        text = text[: MAX_AUDIT_REASON - 1] + "…"
    return text


async def delete_recent_messages(guild: discord.Guild, user_id: int, seconds: int) -> str:
    """刪除使用者在全伺服器指定秒數內的訊息（每頻道最多 50 則），缺權限的頻道略過並計數。"""
    after_time = discord.utils.utcnow() - timedelta(seconds=seconds)
    deleted_total = 0
    skipped_channels = 0
    for channel in guild.text_channels:
        permissions = channel.permissions_for(guild.me)
        if not (permissions.view_channel and permissions.read_message_history and permissions.manage_messages):
            skipped_channels += 1
            continue
        try:
            deleted = await channel.purge(limit=PURGE_LIMIT_PER_CHANNEL, after=after_time, check=lambda m: m.author.id == user_id)
            deleted_total += len(deleted)
        except (discord.Forbidden, discord.HTTPException):
            skipped_channels += 1

    summary = f"最近 {seconds} 秒內全伺服器共刪除 {deleted_total} 則"
    if skipped_channels:
        summary += f"（略過 {skipped_channels} 個頻道）"
    return summary


def _discord_error(e: discord.HTTPException) -> str:
    if isinstance(e, discord.Forbidden):
        return "機器人權限不足，或對象的位階高於機器人"
    return f"Discord 錯誤：{e}"


async def _is_banned(guild: discord.Guild, target: discord.User | discord.Member) -> bool:
    """查詢對象是否已被停權；查詢本身失敗時視為未停權，交給 ban 處理。"""
    try:
        await guild.fetch_ban(discord.Object(id=target.id))
    except discord.NotFound:
        return False
    except discord.HTTPException:
        return False
    return True


async def punish(
    guild: discord.Guild,
    kind: WarningType,
    target: discord.User | discord.Member,
    actor: discord.Member | discord.User,
    reason: str | None,
    *,
    cross_guild: bool,
    duration: timedelta | None = None,
    delete_message_seconds: int | None = None,
    via_dashboard: bool,
) -> PunishResult:
    """執行懲處並寫紀錄。須在 bot 事件迴圈上呼叫。不做位階檢查，交給 Discord 拒絕。"""
    audit = audit_reason(actor, reason, via_dashboard)
    result = PunishResult(ok=False)

    if target.bot:
        result.error = "不能對機器人執行"
        return result
    if target.id == actor.id:
        result.error = "不能對自己執行"
        return result

    if kind in (WarningType.Timeout, WarningType.Kick):
        member = target if isinstance(target, discord.Member) else guild.get_member(target.id)
        if member is None:
            result.error = "對象不在伺服器"
            return result

    if kind == WarningType.Timeout:
        if duration is None or duration <= timedelta(0):
            result.error = "禁言時長錯誤"
            return result
        if duration > MAX_TIMEOUT:
            result.error = "禁言時長不得超過 7 天"
            return result

    try:
        if kind == WarningType.Timeout:
            await member.timeout_for(duration, reason=audit)
            if delete_message_seconds:
                result.deleted_summary = await delete_recent_messages(guild, target.id, delete_message_seconds)
        elif kind == WarningType.Kick:
            await member.kick(reason=audit)
        elif kind == WarningType.Ban:
            if await _is_banned(guild, target):
                result.ok = True
                result.already = True
                return result
            await guild.ban(target, reason=audit, delete_message_seconds=delete_message_seconds or 0)
    except discord.HTTPException as e:
        result.error = _discord_error(e)
        return result

    result.ok = True

    try:
        result.warning_id = sclient.sqldb.add_warning(
            target.id, kind, actor.id, guild.id, nowtz(), reason, duration if kind == WarningType.Timeout else None, guild_only=not cross_guild
        )
    except Exception:
        log.exception("punish: action done but add_warning failed")
        result.error = "動作已執行，但紀錄寫入失敗"
        return result

    if kind == WarningType.Warning and _after_warning is not None:
        try:
            result.auto_timeout = await _after_warning(guild, target, result.warning_id)
        except Exception as e:
            log.exception("after_warning hook failed")
            result.auto_timeout = AutoTimeoutResult(ok=False, error=f"自動禁言執行失敗：{e}")
    return result


def announcement(result: PunishResult, target: discord.User | discord.Member, actor: discord.Member | discord.User) -> dict:
    """產生公告訊息的 send 參數：@ 對象加上含紀錄編號的警告單 embed。"""
    embed = None
    if result.warning_id is not None:
        row = sclient.sqldb.get_warning(result.warning_id)
        if row is not None:
            embed = row.embed(sclient.bot)
    if embed is None:
        embed = BotEmbed.general(f"{target.name} 已被處置", target.display_avatar.url, description=f"{target.mention}")
        embed.add_field(name="執行人員", value=actor.mention)

    if result.deleted_summary:
        embed.add_field(name="訊息刪除", value=result.deleted_summary, inline=False)
    if result.auto_timeout is not None:
        auto = result.auto_timeout
        value = f"已禁言 {auto.duration}" if auto.ok else f"失敗：{auto.error}"
        embed.add_field(name="自動禁言", value=value, inline=False)

    return {
        "content": target.mention,
        "embed": embed,
        "allowed_mentions": discord.AllowedMentions(everyone=False, roles=False, replied_user=False, users=[discord.Object(id=target.id)]),
    }
