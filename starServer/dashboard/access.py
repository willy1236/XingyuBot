"""伺服器存取檢查與 bot 端的 Discord 讀取，T-04～T-09 共用。"""

import asyncio
from collections.abc import Callable

import discord
from fastapi import Depends

from starlib import sclient

from .errors import DashboardError
from .guilds import guild_perms
from .session import SessionInfo, require_session


async def on_guild[T](guild_id: int, fn: Callable[[discord.Guild], T]) -> T:
    """在 bot 的事件迴圈上對該伺服器執行 fn（讀 Discord 物件一律經這裡）。

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
        return fn(guild)

    return await asyncio.wrap_future(bot.submit(_run()))


async def require_guild_access(guild_id: int, info: SessionInfo = Depends(require_session)) -> int:
    """依序確認 session、使用者有 Manage Channels、bot 在該伺服器；回傳 guild_id。

    錯誤：401 session_expired／reauth_required、403 no_permission、404 bot_not_in_guild、503 bot_unavailable。
    """
    if not (await guild_perms(info.discord_user_id, guild_id)).manage_channels:
        raise DashboardError(403, "no_permission")
    await on_guild(guild_id, lambda _guild: None)
    return guild_id
