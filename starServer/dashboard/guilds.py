"""伺服器清單：使用者在 Discord 的伺服器與權限（10 分鐘快取），以及 GET /dashboard/guilds。

其他卡用 guild_perms 判斷權限、用 invalidate 清快取。授權失效與 Discord 暫時不可用都直接拋 DashboardError，
呼叫端不必再轉換。
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import timedelta

import httpx
from authlib.integrations.base_client.errors import OAuthError
from fastapi import APIRouter, Depends

from starlib import sclient, sqldb
from starlib.database import OAuthToken
from starlib.oauth import DiscordOAuth
from starlib.utils import nowtz

from . import auth
from .db import run_db
from .errors import DashboardError
from .session import SessionInfo, require_session

log = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard")

CACHE_TTL = 600
# token 剩不到這麼久就先 refresh，避免送出請求途中過期
REFRESH_MARGIN = timedelta(seconds=60)

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
class UserGuild:
    id: str
    name: str
    icon: str | None
    owner: bool
    permissions: int

    @property
    def full_access(self) -> bool:
        return self.owner or bool(self.permissions & ADMINISTRATOR)


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


# user_id -> (抓取時間, 清單)。過期的項目保留，Discord 暫時不可用時沿用
_cache: dict[str, tuple[float, list[UserGuild]]] = {}


def invalidate(user_id: str) -> None:
    """清掉該使用者的快取，下一次請求一定重抓。登入、登出與邀請 bot 之後呼叫。"""
    _cache.pop(user_id, None)


auth.on_auth_change(invalidate)


def _reauth() -> DashboardError:
    return DashboardError(401, "reauth_required")


def _unavailable() -> DashboardError:
    return DashboardError(502, "discord_unavailable")


def _load_token(user_id: str, credential_id: int) -> OAuthToken | None:
    """讀出 token 並複製成不綁 session 的物件，離開 run_db 後仍可安全存取。"""
    row = sqldb.get_oauth_token(user_id, credential_id)
    if row is None:
        return None
    return OAuthToken(
        user_id=row.user_id,
        client_credential_id=row.client_credential_id,
        access_token=row.access_token,
        refresh_token=row.refresh_token,
        scope=list(row.scope),
        expires_at=row.expires_at,
    )


async def _refresh(oauth: DiscordOAuth, user_id: str, old: OAuthToken) -> None:
    """用 refresh token 換新並寫回資料庫。OAuth2Base.refresh() 本身不寫回。"""
    if not old.refresh_token:
        raise _reauth()
    token = await oauth.refresh(old.refresh_token)
    # to_db_token 傳的是 OAuthToken 沒有的 credential_id，主鍵欄位 client_credential_id 要自己補
    fresh = oauth.to_db_token(token)
    fresh.client_credential_id = oauth._credential_id  # pyright: ignore[reportAttributeAccessIssue]
    if "guilds" not in fresh.scope:
        raise _reauth()
    oauth.db_token = fresh
    await run_db(lambda: oauth.save_token_to_db(user_id))
    # save_token_to_db 會換成綁著 session 的物件，離開 run_db 後不能安全存取，改回未綁定的副本
    oauth.db_token = fresh
    oauth.scopes = fresh.scope


async def _fetch(user_id: str) -> list[UserGuild]:
    client = await auth.get_oauth_client()
    row = await run_db(lambda: _load_token(user_id, client.credential_id))
    if row is None or "guilds" not in row.scope:
        raise _reauth()
    try:
        async with DiscordOAuth.create_from_db(client, scopes=list(row.scope)) as oauth:
            oauth.db_token = row
            if row.expires_at <= nowtz() + REFRESH_MARGIN:
                await _refresh(oauth, user_id, row)
            data = await oauth.api_get("/users/@me/guilds")
    except DashboardError:
        raise
    except OAuthError:
        # refresh token 已失效或被撤銷
        raise _reauth() from None
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401:
            raise _reauth() from None
        log.warning("Discord /users/@me/guilds failed: %s", exc)
        raise _unavailable() from None
    except httpx.HTTPError as exc:
        log.warning("Discord /users/@me/guilds network error: %s", exc)
        raise _unavailable() from None
    return [
        UserGuild(
            id=str(g["id"]),
            name=g["name"],
            icon=g.get("icon"),
            owner=bool(g.get("owner")),
            permissions=int(g.get("permissions") or 0),
        )
        for g in data
    ]


async def get_user_guilds(user_id: str, refresh: bool = False) -> list[UserGuild]:
    """使用者所在的伺服器。10 分鐘快取；refresh=True 略過快取。

    Raises:
        DashboardError: 401 reauth_required（授權失效），或 502 discord_unavailable（Discord 暫時不可用且沒有舊快取）。
    """
    # 同一個使用者的重抓與 refresh 序列化：refresh token 用一次就換新，同時 refresh 第二次會失敗而被誤判成授權失效
    async with auth.user_lock(user_id):
        entry = _cache.get(user_id)
        if entry is not None and not refresh and time.monotonic() - entry[0] < CACHE_TTL:
            return entry[1]
        try:
            guilds = await _fetch(user_id)
        except DashboardError as exc:
            if exc.code == "discord_unavailable" and entry is not None:
                return entry[1]
            if exc.code == "reauth_required":
                invalidate(user_id)
            raise
        _cache[user_id] = (time.monotonic(), guilds)
        return guilds


async def guild_perms(user_id: str, guild_id: str | int) -> GuildPerms:
    """使用者在該伺服器的權限；Administrator 與擁有者視同全部，不在清單裡視同沒有。"""
    gid = str(guild_id)
    for g in await get_user_guilds(user_id):
        if g.id == gid:
            return GuildPerms(g.permissions, g.full_access)
    return GuildPerms()


async def bot_guild_ids() -> set[str]:
    """bot 目前所在的伺服器 ID。bot 尚未 ready 時回 503 bot_unavailable，避免把所有伺服器誤判成 bot 不在。"""
    bot = sclient.bot
    if bot is None or not bot.is_ready():
        raise DashboardError(503, "bot_unavailable")

    async def _ids() -> set[str]:
        return {str(g.id) for g in bot.guilds}

    return await asyncio.wrap_future(bot.submit(_ids()))


def _icon_url(guild: UserGuild) -> str | None:
    if not guild.icon:
        return None
    ext = "gif" if guild.icon.startswith("a_") else "png"
    return f"https://cdn.discordapp.com/icons/{guild.id}/{guild.icon}.{ext}"


def _item(guild: UserGuild) -> dict:
    return {"id": guild.id, "name": guild.name, "icon_url": _icon_url(guild)}


@router.get("/guilds")
async def list_guilds(refresh: int = 0, info: SessionInfo = Depends(require_session)):
    bot_ids = await bot_guild_ids()
    guilds = await get_user_guilds(info.discord_user_id, refresh=bool(refresh))
    invited: list[UserGuild] = []
    not_invited: list[UserGuild] = []
    for g in guilds:
        if g.id in bot_ids:
            if can_enter(GuildPerms(g.permissions, g.full_access)):
                invited.append(g)
        elif g.full_access or g.permissions & MANAGE_GUILD:
            not_invited.append(g)
    key = lambda g: g.name.casefold()  # noqa: E731
    return {
        "invited": [_item(g) for g in sorted(invited, key=key)],
        "not_invited": [_item(g) for g in sorted(not_invited, key=key)],
    }
