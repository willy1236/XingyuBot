"""在 bot 端讀 Discord 使用者的名稱與頭像（析域登入的候選、個人區的 Discord 清單共用）。"""

import asyncio
import logging
from dataclasses import dataclass

from starlib import sclient

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DiscordProfile:
    name: str
    #: 頭像 hash；沒有自訂頭像時為 None
    avatar: str | None


async def fetch_discord_user(discord_id: int) -> DiscordProfile | None:
    """在 bot 的事件迴圈上取 Discord 使用者：先查快取，沒有再向 Discord 查；bot 不可用或查不到時回 None。"""
    bot = sclient.bot
    if bot is None:
        return None

    async def _get() -> DiscordProfile:
        user = bot.get_user(discord_id) or await bot.fetch_user(discord_id)
        return DiscordProfile(user.global_name or user.name, user.avatar.key if user.avatar else None)

    try:
        return await asyncio.wrap_future(bot.submit(_get()))
    except Exception as exc:
        log.warning("Discord user %s unavailable: %r", discord_id, exc)
        return None
