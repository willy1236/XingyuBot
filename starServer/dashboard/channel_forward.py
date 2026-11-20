"""實況主後台：把頻道的事件轉發到 Discord 頻道。

GET /dashboard/channels/{twitch_id}/forward          目前的轉發設定與 `editable`
GET /dashboard/channels/{twitch_id}/forward/options  bot 在、且 session 的 Discord 有 Manage Channels 的伺服器與文字頻道
PUT /dashboard/channels/{twitch_id}/forward          body `{guild_id, channel_id | null}`；`channel_id` 為 null 時清除設定

只有析域登入且有 Discord 的 session 可以修改或取得選項（`channels.forward_access == "ok"`）；
只用 Twitch 登入時 GET 仍回目前設定，`editable` 為 false。
權限不用 `no_permission`：前端在全域把它當成伺服器權限處理，會導走整個頁面。
修改不要求頻道已啟用；設定寫進 `TwitchBotJoinChannel.action_channel_id` 與 `action_guild_id`，
Discord 端每次發送都讀 DB，不必通知 Twitch bot。
"""

import asyncio

import discord
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from starlib import sclient, sqldb, twitch_audit
from starlib.database import TwitchBotJoinChannel

from .access import ensure_guild_available, on_guild
from .channels import DEFAULT_STATE, forward_access, require_channel
from .db import run_db
from .errors import DashboardError
from .guilds import bot_guild_ids, guild_perms
from .session import DiscordSessionInfo, SessionInfo, TwitchIdentity, audit_actor, require_any_session
from .validity import channel_invalid_reason

router = APIRouter(prefix="/dashboard")


class PutBody(BaseModel):
    guild_id: int | None = None
    channel_id: int | None = None


def _require_editable(info: SessionInfo) -> DiscordSessionInfo:
    """析域登入且有 Discord 才能修改轉發；回傳的 session 一定帶 discord_user_id。

    Raises:
        DashboardError: 403 forward_not_allowed。
    """
    if forward_access(info) != "ok":
        raise DashboardError(403, "forward_not_allowed")
    return info  # type: ignore[return-value]


def _guild_info(guild: discord.Guild) -> dict:
    return {"id": str(guild.id), "name": guild.name, "icon_url": guild.icon.url if guild.icon else None}


def _text_channels(guild: discord.Guild) -> list[dict]:
    """bot 能在其中發言的文字與公告頻道，依 position 排序。須在 bot 的事件迴圈上呼叫。"""
    return [
        {"id": str(c.id), "name": c.name, "type": c.type.name}
        for c in sorted(guild.channels, key=lambda c: (c.position, c.id))
        if channel_invalid_reason(guild, c.id, False) is None
    ]


async def _current(config: TwitchBotJoinChannel | None) -> dict:
    """目前設定的伺服器與頻道名稱，讀 bot 的快取；bot 沒 ready 或找不到時名稱為 None，不因此回錯誤。

    舊的頻道列只有 action_channel_id、沒有 action_guild_id，伺服器由頻道取得。
    """
    channel_id = None if config is None else config.action_channel_id
    if not channel_id:
        return {"guild": None, "channel": None}
    guild_id = config.action_guild_id  # type: ignore[union-attr]
    bot = sclient.bot

    def lookup() -> tuple[int | None, str | None, str | None]:
        channel = bot.get_channel(channel_id)  # type: ignore[union-attr]
        guild = bot.get_guild(guild_id) if guild_id else getattr(channel, "guild", None)  # type: ignore[union-attr]
        return (
            guild.id if guild is not None else guild_id,
            guild.name if guild is not None else None,
            getattr(channel, "name", None),
        )

    found: tuple[int | None, str | None, str | None] = (guild_id, None, None)
    if bot is not None and bot.is_ready():

        async def _lookup():
            return lookup()

        found = await asyncio.wrap_future(bot.submit(_lookup()))
    resolved_guild_id, guild_name, channel_name = found
    return {
        "guild": None if resolved_guild_id is None else {"id": str(resolved_guild_id), "name": guild_name},
        "channel": {"id": str(channel_id), "name": channel_name},
    }


def _config(twitch_id: int) -> TwitchBotJoinChannel | None:
    return sqldb.get_twitch_join_channel(twitch_id)


@router.get("/channels/{twitch_id}/forward")
async def get_forward(
    twitch_id: int,
    info: SessionInfo = Depends(require_any_session),
    _channel: TwitchIdentity = Depends(require_channel),
):
    config = await run_db(lambda: _config(twitch_id))
    return {"editable": forward_access(info) == "ok", **await _current(config)}


@router.get("/channels/{twitch_id}/forward/options")
async def get_forward_options(
    twitch_id: int,
    info: SessionInfo = Depends(require_any_session),
    _channel: TwitchIdentity = Depends(require_channel),
):
    session_info = _require_editable(info)
    user_id = session_info.discord_user_id

    async def allowed(guild_id: str) -> bool:
        return (await guild_perms(user_id, guild_id)).manage_channels

    ids = sorted(await bot_guild_ids())
    flags = await asyncio.gather(*(allowed(i) for i in ids))
    guilds = []
    for guild_id in (i for i, ok in zip(ids, flags, strict=True) if ok):
        try:
            guild = await on_guild(int(guild_id), lambda g: {**_guild_info(g), "channels": _text_channels(g)})
        except DashboardError as e:
            if e.code == "bot_not_in_guild":  # 查詢途中 bot 被踢出
                continue
            raise
        guilds.append(guild)
    return {"guilds": sorted(guilds, key=lambda x: x["name"].casefold())}


async def _verify(user_id: str, guild_id: int, channel_id: int) -> None:
    """伺服器端重新檢查：使用者在該伺服器有 Manage Channels，且頻道屬於它、是 bot 能發言的文字頻道。

    Raises:
        DashboardError: 403 forward_forbidden；400 invalid_channel；404 bot_not_in_guild；503 bot_unavailable、guild_unavailable。
    """
    if not (await guild_perms(user_id, guild_id)).manage_channels:
        raise DashboardError(403, "forward_forbidden")

    def check(guild: discord.Guild) -> None:
        ensure_guild_available(guild)
        if channel_invalid_reason(guild, channel_id, False) is not None:
            raise DashboardError(400, "invalid_channel")

    await on_guild(guild_id, check)


def _snapshot(config: TwitchBotJoinChannel | None) -> dict | None:
    if config is None or not config.action_channel_id:
        return None
    return {
        "guild_id": None if config.action_guild_id is None else str(config.action_guild_id),
        "channel_id": str(config.action_channel_id),
    }


def _save(twitch_id: int, actor: twitch_audit.AuditActor, guild_id: int | None, channel_id: int | None) -> None:
    """寫入設定與修改紀錄（同一個交易）；設定沒變就什麼都不寫。"""
    try:
        config = _config(twitch_id)
        before = _snapshot(config)
        after = None if channel_id is None else {"guild_id": str(guild_id), "channel_id": str(channel_id)}
        if before == after:
            return
        if config is None:
            config = TwitchBotJoinChannel(twitch_id=twitch_id, state=DEFAULT_STATE)  # pyright: ignore[reportCallIssue]
        config.action_channel_id = channel_id
        config.action_guild_id = None if channel_id is None else guild_id
        sqldb.session.add(config)
        action = "create" if before is None else "delete" if after is None else "update"
        twitch_audit.record_change(twitch_id, actor, "dashboard", "forward", "discord", action, before, after)
        sqldb.commit()
    except Exception:
        sqldb.session.rollback()
        raise


@router.put("/channels/{twitch_id}/forward")
async def put_forward(
    twitch_id: int,
    body: PutBody,
    info: SessionInfo = Depends(require_any_session),
    _channel: TwitchIdentity = Depends(require_channel),
):
    session_info = _require_editable(info)
    if body.channel_id is not None:
        if body.guild_id is None:
            raise DashboardError(400, "invalid_request")
        await _verify(session_info.discord_user_id, body.guild_id, body.channel_id)
    actor = audit_actor(info)
    await run_db(lambda: _save(twitch_id, actor, body.guild_id, body.channel_id))
    config = await run_db(lambda: _config(twitch_id))
    return {"editable": True, **await _current(config)}
