"""伺服器存取檢查與 bot 端的 Discord 讀取，T-04～T-09 共用。"""

import asyncio
from collections.abc import Awaitable, Callable
from enum import StrEnum

import discord
from fastapi import Depends

from starlib import sclient

from .errors import DashboardError
from .guilds import (
    BAN_MEMBERS,
    ENTRY_BITS,
    KICK_MEMBERS,
    MANAGE_CHANNELS,
    MANAGE_GUILD,
    MANAGE_MESSAGES,
    MANAGE_ROLES,
    MODERATE_MEMBERS,
    GuildPerms,
    guild_perms,
)
from .session import SessionInfo, require_session


async def on_guild_async[T](guild_id: int, fn: Callable[[discord.Guild], Awaitable[T]]) -> T:
    """在 bot 的事件迴圈上對該伺服器執行 coroutine fn（需要 await Discord 呼叫時用，例如發訊息）。

    Raises:
        DashboardError: 503 bot_unavailable（bot 尚未 ready）；404 bot_not_in_guild（bot 不在該伺服器）。
    """
    bot = sclient.bot
    if bot is None or not bot.is_ready():
        raise DashboardError(503, "bot_unavailable")

    async def _run() -> T:
        guild = bot.get_guild(guild_id)
        if guild is None:
            raise DashboardError(404, "bot_not_in_guild")
        return await fn(guild)

    return await asyncio.wrap_future(bot.submit(_run()))


async def on_guild[T](guild_id: int, fn: Callable[[discord.Guild], T]) -> T:
    """在 bot 的事件迴圈上對該伺服器執行 fn（讀 Discord 物件一律經這裡）。

    Raises:
        DashboardError: 503 bot_unavailable（bot 尚未 ready）；404 bot_not_in_guild（bot 不在該伺服器）。
    """

    async def _call(guild: discord.Guild) -> T:
        return fn(guild)

    return await on_guild_async(guild_id, _call)


def ensure_guild_available(guild: discord.Guild) -> None:
    """伺服器 unavailable（Discord outage）時 guild 在快取裡但頻道與身分組是空的，快取判斷「不存在」不可信。

    依快取決定刪除、覆寫或標示失效的端點，進入後先呼叫這個函式。

    Raises:
        DashboardError: 503 guild_unavailable。
    """
    if guild.unavailable:
        raise DashboardError(503, "guild_unavailable")


class Section(StrEnum):
    """伺服器頁的區塊；宣告順序即側欄顯示順序。"""

    NOTIFY = "notify"
    DYNAMIC_VOICE = "dynamic_voice"
    REACTION_ROLES = "reaction_roles"
    TICKETS = "tickets"
    WARNINGS = "warnings"
    GIVEAWAYS = "giveaways"
    SETTINGS = "settings"


#: 區塊 -> 動作 -> 需要的權限（擁有其中任一項即可）。`view` 是進入該區塊；Administrator 與擁有者視同全部。
SECTION_RULES: dict[Section, dict[str, tuple[int, ...]]] = {
    Section.NOTIFY: {"view": (MANAGE_CHANNELS,)},
    Section.DYNAMIC_VOICE: {"view": (MANAGE_CHANNELS,)},
    Section.REACTION_ROLES: {"view": (MANAGE_ROLES,)},
    Section.TICKETS: {"view": (MANAGE_CHANNELS,)},
    Section.WARNINGS: {
        "view": ENTRY_BITS,  # 與指令的查詢不需權限一致：能進入伺服器頁即可
        "add": (MANAGE_MESSAGES,),
        "remove": (KICK_MEMBERS, BAN_MEMBERS, MANAGE_MESSAGES),
        "timeout": (MODERATE_MEMBERS,),
        "kick": (KICK_MEMBERS,),
        "ban": (BAN_MEMBERS,),
    },
    Section.GIVEAWAYS: {
        "view": (MANAGE_MESSAGES,),
        "end": (MANAGE_MESSAGES,),
        "redraw": (MANAGE_MESSAGES,),
    },
    Section.SETTINGS: {"view": (MANAGE_GUILD,)},
}


def section_actions(perms: GuildPerms, section: Section) -> list[str]:
    """使用者在該區塊擁有的動作；沒有 `view` 權限就是沒有這個區塊，回空串列。"""
    rules = SECTION_RULES[section]
    if not perms.has_any(rules["view"]):
        return []
    return [action for action, bits in rules.items() if perms.has_any(bits)]


def require_section(section: Section, action: str | None = None):
    """dependency factory：依序確認 session、使用者有該區塊（動作）的權限、bot 在該伺服器；回傳 guild_id。

    action 省略時只要求進入該區塊（`view`）。

    錯誤：401 session_expired／reauth_required、403 no_permission、404 bot_not_in_guild、503 bot_unavailable。
    """
    bits = SECTION_RULES[section][action or "view"]  # 寫錯動作名稱在 import 時就失敗

    async def dependency(guild_id: int, info: SessionInfo = Depends(require_session)) -> int:
        if not (await guild_perms(info.discord_user_id, guild_id)).has_any(bits):
            raise DashboardError(403, "no_permission")
        await on_guild(guild_id, lambda _guild: None)
        return guild_id

    return dependency


#: 通知與動態語音等既有端點用：Manage Channels
require_guild_access = require_section(Section.NOTIFY)
