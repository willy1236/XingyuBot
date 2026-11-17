"""在 bot 端讀 Discord 使用者的名稱與頭像（析域登入的候選、個人區的 Discord 清單共用）。"""

import asyncio
import logging
import time
from dataclasses import dataclass

from starlib import sclient

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DiscordProfile:
    name: str
    #: 頭像 hash；沒有自訂頭像時為 None
    avatar: str | None


#: 向 Discord 查到（不在 bot 快取裡）的使用者保留多久（秒），個人區每次載入才不會都打一次 Discord API
FETCHED_TTL = 600.0
# Discord ID -> (到期時間 monotonic, 查到的使用者)
_fetched: dict[int, tuple[float, DiscordProfile]] = {}


def _profile(user) -> DiscordProfile:
    return DiscordProfile(user.global_name or user.name, user.avatar.key if user.avatar else None)


async def fetch_discord_user(discord_id: int) -> DiscordProfile | None:
    """在 bot 的事件迴圈上取 Discord 使用者：先查 bot 的快取，沒有再向 Discord 查（結果保留 10 分鐘）；
    bot 不可用或查不到時回 None。"""
    bot = sclient.bot
    if bot is None:
        return None

    now = time.monotonic()
    cached = _fetched.get(discord_id)

    async def _get() -> tuple[DiscordProfile, bool]:
        user = bot.get_user(discord_id)
        if user is not None:
            return _profile(user), False
        if cached is not None and cached[0] > now:
            return cached[1], False
        return _profile(await bot.fetch_user(discord_id)), True

    try:
        profile, fetched = await asyncio.wrap_future(bot.submit(_get()))
    except Exception as exc:
        log.warning("Discord user %s unavailable: %r", discord_id, exc)
        return None
    if fetched:
        for key in [k for k, (expires, _) in _fetched.items() if expires <= now]:
            del _fetched[key]
        _fetched[discord_id] = (now + FETCHED_TTL, profile)
    return profile
