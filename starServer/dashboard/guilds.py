"""伺服器清單與權限：由 bot 的成員快取判斷使用者在各伺服器的權限，以及 GET /dashboard/guilds。

網站不保存使用者的 Discord 授權；權限一律以 bot 當下看到的成員資料為準，Discord 端拔掉權限立即生效。
"""

import asyncio
from dataclasses import dataclass

import discord
from fastapi import APIRouter, Depends

from starlib import sclient

from .errors import DashboardError
from .session import DiscordSessionInfo, require_session

router = APIRouter(prefix="/dashboard")

# Discord permission bits（https://discord.com/developers/docs/topics/permissions）
KICK_MEMBERS = 0x2
BAN_MEMBERS = 0x4
ADMINISTRATOR = 0x8
MANAGE_CHANNELS = 0x10
MANAGE_GUILD = 0x20
MANAGE_MESSAGES = 0x2000
MANAGE_ROLES = 0x10000000
MODERATE_MEMBERS = 0x10000000000

#: 進入伺服器頁的條件：擁有其中任一項（Administrator 與擁有者視同全部）
ENTRY_BITS = (
    MANAGE_CHANNELS,
    MANAGE_ROLES,
    MANAGE_GUILD,
    MANAGE_MESSAGES,
    KICK_MEMBERS,
    BAN_MEMBERS,
    MODERATE_MEMBERS,
)


@dataclass(frozen=True)
class GuildPerms:
    """使用者在某伺服器的權限：permission bits，full 為 True（Administrator 或擁有者）時視同全部。"""

    bits: int = 0
    full: bool = False

    def has_any(self, bits: tuple[int, ...]) -> bool:
        """是否擁有 bits 其中任一項；bits 為空時視為沒有任何權限滿足。"""
        return self.full or any(self.bits & b for b in bits)

    @property
    def manage_channels(self) -> bool:
        return self.has_any((MANAGE_CHANNELS,))

    @property
    def manage_guild(self) -> bool:
        return self.has_any((MANAGE_GUILD,))


def can_enter(perms: GuildPerms) -> bool:
    """是否符合進入伺服器頁的條件（擁有 ENTRY_BITS 任一項）。"""
    return perms.has_any(ENTRY_BITS)


def _member_perms(guild: discord.Guild, user_id: int) -> GuildPerms:
    """依 bot 的成員快取判斷使用者在該伺服器的權限；不是成員視同沒有。須在 bot 的事件迴圈上呼叫。

    擁有者不靠成員快取判斷：大型伺服器剛加入時成員還沒載入完，擁有者邀請後仍要能直接進入。
    """
    if guild.owner_id == user_id:
        return GuildPerms(0, True)
    member = guild.get_member(user_id)
    if member is None:
        return GuildPerms()
    perms = member.guild_permissions
    return GuildPerms(perms.value, perms.administrator)


def _ready_bot():
    bot = sclient.bot
    if bot is None or not bot.is_ready():
        raise DashboardError(503, "bot_unavailable")
    return bot


async def guild_perms(user_id: str, guild_id: str | int) -> GuildPerms:
    """使用者在該伺服器的權限，由 bot 的成員快取判斷；Administrator 與擁有者視同全部，不是成員視同沒有。

    Raises:
        DashboardError: 503 bot_unavailable（bot 尚未 ready）；404 bot_not_in_guild（bot 不在該伺服器）。
    """
    bot = _ready_bot()

    async def _perms() -> GuildPerms:
        guild = bot.get_guild(int(guild_id))
        if guild is None:
            raise DashboardError(404, "bot_not_in_guild")
        return _member_perms(guild, int(user_id))

    return await asyncio.wrap_future(bot.submit(_perms()))


async def bot_guild_ids() -> set[str]:
    """bot 目前所在的伺服器 ID。bot 尚未 ready 時回 503 bot_unavailable，避免把所有伺服器誤判成 bot 不在。"""
    bot = _ready_bot()

    async def _ids() -> set[str]:
        return {str(g.id) for g in bot.guilds}

    return await asyncio.wrap_future(bot.submit(_ids()))


def _icon_url(guild: discord.Guild) -> str | None:
    return guild.icon.url if guild.icon else None


@router.get("/guilds")
async def list_guilds(info: DiscordSessionInfo = Depends(require_session)):
    """bot 所在、且使用者符合進入條件的伺服器，依名稱排序。"""
    bot = _ready_bot()
    user_id = int(info.discord_user_id)

    async def _list() -> list[dict]:
        items = [
            {"id": str(g.id), "name": g.name, "icon_url": _icon_url(g)}
            for g in bot.guilds
            if can_enter(_member_perms(g, user_id))
        ]
        return sorted(items, key=lambda x: x["name"].casefold())

    return {"guilds": await asyncio.wrap_future(bot.submit(_list()))}
