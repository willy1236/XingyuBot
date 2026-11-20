"""bot owner 營運入口的 Discord 部分：目前所在的伺服器、每日人數，與加入離開紀錄。

GET /dashboard/ops/discord?days=        目前所在的伺服器與總數（bot 沒就緒時 live 是 null），以及最近 days 天的每日人數
GET /dashboard/ops/discord/events?page= 伺服器加入、離開紀錄（新的在前，每頁 50 筆）
GET /dashboard/ops/discord/lookup?id=&channel_id=  用 ID 查使用者、頻道、伺服器、身分組，給頻道 ID 時一併查訊息

權限同 `ops.py`：只放行 bot owner，不是回 403 not_bot_owner。
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any

import discord
from fastapi import APIRouter, Depends

from starlib import sclient, sqldb
from starlib.utils import nowtz

from .db import run_db
from .errors import DashboardError
from .ops import PAGE_SIZE, require_bot_owner
from .session import SessionInfo

router = APIRouter(prefix="/dashboard/ops/discord")

DAYS_DEFAULT = 365
DAYS_MAX = 3650


def _guild_json(guild: discord.Guild) -> dict[str, Any]:
    me = guild.me
    joined_at = me.joined_at if me else None
    return {
        "id": str(guild.id),
        "name": guild.name,
        "icon_url": guild.icon.url if guild.icon else None,
        "member_count": guild.member_count,
        "joined_at": None if joined_at is None else joined_at.isoformat(),
        "owner": _owner_json(guild),
    }


def _owner_json(guild: discord.Guild) -> dict[str, Any] | None:
    """群主；成員快取還沒有群主時只有 id，名稱與頭像為 null。伺服器資料不完整時整個是 null。"""
    if guild.owner_id is None:
        return None
    owner = guild.owner
    return {
        "id": str(guild.owner_id),
        "name": None if owner is None else owner.display_name,
        "avatar_url": None if owner is None else owner.display_avatar.url,
    }


def _live() -> dict[str, Any] | None:
    bot = sclient.bot
    if bot is None or not bot.is_ready():
        return None
    guilds = sorted(bot.guilds, key=lambda g: g.me.joined_at if g.me and g.me.joined_at else nowtz(), reverse=True)
    return {
        "guild_count": len(guilds),
        "user_count": len(bot.users),
        "guilds": [_guild_json(g) for g in guilds],
    }


@router.get("")
async def overview(days: int = DAYS_DEFAULT, _: SessionInfo = Depends(require_bot_owner)):
    since = nowtz().date() - timedelta(days=min(max(days, 1), DAYS_MAX) - 1)
    records = await run_db(lambda: sqldb.list_users_count_records(since))
    return {
        "live": _live(),
        "daily": [
            {"date": r.record_date.isoformat(), "users": r.users_count, "servers": r.servers_count} for r in records
        ],
    }


@router.get("/events")
async def list_events(page: int = 1, _: SessionInfo = Depends(require_bot_owner)):
    page = max(page, 1)
    # 多讀一筆判斷有沒有下一頁
    rows = await run_db(lambda: sqldb.list_guild_membership_events((page - 1) * PAGE_SIZE, PAGE_SIZE + 1))
    return {
        "events": [
            {
                "id": r.id,
                "guild_id": str(r.guild_id),
                "guild_name": r.guild_name,
                "event": r.event,
                "member_count": r.member_count,
                "at": r.at.isoformat(),
                "source": r.source,
            }
            for r in rows[:PAGE_SIZE]
        ],
        "page": page,
        "has_next": len(rows) > PAGE_SIZE,
    }


# ====== ID 查詢 ======

SNOWFLAKE_MAX = 2**64 - 1


def _parse_id(raw: str) -> int:
    """1 到 2^64-1 的整數 ID；否則 400 invalid_id。"""
    if not raw.isascii() or not raw.isdigit() or not 1 <= int(raw) <= SNOWFLAKE_MAX:
        raise DashboardError(400, "invalid_id")
    return int(raw)


def _iso(at: datetime | None) -> str | None:
    return None if at is None else at.isoformat()


def _guild_ref(guild: discord.Guild) -> dict[str, Any]:
    return {"id": str(guild.id), "name": guild.name, "icon_url": guild.icon.url if guild.icon else None}


def _mutual_json(bot: discord.Client, guild: discord.Guild, user_id: int) -> dict[str, Any]:
    """共同伺服器的一列。沒有 presence intent 時狀態與活動為 null（不明），不當成離線。"""
    member = guild.get_member(user_id)
    if member is None:
        return {"guild": _guild_ref(guild), "member": None}
    presences = bot.intents.presences
    activity = member.activity if presences else None
    return {
        "guild": _guild_ref(guild),
        "member": {
            "nick": member.nick,
            "top_role": {"id": str(member.top_role.id), "name": member.top_role.name},
            "joined_at": _iso(member.joined_at),
            "timed_out": member.timed_out,
            "status": member.raw_status if presences else None,
            "activity": None if activity is None else activity.name,
        },
    }


async def _lookup_user(bot: discord.Client, target: int) -> dict[str, Any] | None:
    user = bot.get_user(target)
    if user is None:
        try:
            user = await bot.fetch_user(target)
        except discord.NotFound:
            return None
        except discord.HTTPException as exc:
            # ID 超出範圍等格式問題 Discord 回 400，等同查不到；rate limit、5xx 才是暫時查不到
            if exc.status == 400:
                return None
            return {"kind": "user", "error": "unavailable"}
    return {
        "kind": "user",
        "id": str(user.id),
        "name": user.global_name or user.name,
        "username": user.name,
        "avatar_url": user.display_avatar.url,
        "created_at": _iso(user.created_at),
        "bot": user.bot,
        "system": user.system,
        "guilds": [_mutual_json(bot, g, user.id) for g in user.mutual_guilds],
    }


def _lookup_channel(bot: discord.Client, target: int) -> dict[str, Any] | None:
    """頻道與討論串都只認快取中的。"""
    channel = bot.get_channel(target)
    if channel is None:
        return None
    category = getattr(channel, "category", None)
    guild = getattr(channel, "guild", None)
    return {
        "kind": "channel",
        "id": str(channel.id),
        "name": getattr(channel, "name", None),
        "type": str(channel.type),
        "category": None if category is None else {"id": str(category.id), "name": category.name},
        "guild": None if guild is None else _guild_ref(guild),
        "created_at": _iso(channel.created_at),
    }


def _lookup_guild(bot: discord.Client, target: int) -> dict[str, Any] | None:
    guild = bot.get_guild(target)
    if guild is None:
        return None
    return {
        "kind": "guild",
        **_guild_ref(guild),
        "owner": _owner_json(guild),
        "member_count": guild.member_count,
        "text_channels": len(guild.text_channels),
        "voice_channels": len(guild.voice_channels),
        "verification_level": str(guild.verification_level),
        "created_at": _iso(guild.created_at),
    }


def _lookup_role(bot: discord.Client, target: int) -> dict[str, Any] | None:
    for guild in bot.guilds:
        role = guild.get_role(target)
        # @everyone 與伺服器同 ID，已由伺服器卡片代表
        if role is None or role.is_default():
            continue
        return {
            "kind": "role",
            "id": str(role.id),
            "name": role.name,
            "guild": _guild_ref(guild),
            "position": role.position,
            "color": None if role.color.value == 0 else str(role.color),
            # 權限位元可能超過 JS 能精確表示的整數
            "permissions": str(role.permissions.value),
        }
    return None


def _content_hidden(bot: discord.Client, message: discord.Message) -> bool:
    """沒有 message content intent 時伺服器訊息讀不到內容（提及星羽、星羽自己發的除外），與空訊息分開。"""
    if message.content or bot.intents.message_content or message.guild is None:
        return False
    me = bot.user
    return me is None or (message.author.id != me.id and all(m.id != me.id for m in message.mentions))


async def _lookup_message(bot: discord.Client, target: int, channel_id: int) -> dict[str, Any] | None:
    channel = bot.get_channel(channel_id)
    if channel is None or not hasattr(channel, "fetch_message"):
        return {"kind": "message", "error": "channel_not_found"}
    try:
        message: discord.Message = await channel.fetch_message(target)  # pyright: ignore[reportAttributeAccessIssue]
    except discord.NotFound:
        return None
    except discord.Forbidden:
        return {"kind": "message", "error": "forbidden"}
    except discord.HTTPException:
        return {"kind": "message", "error": "unavailable"}
    author = message.author
    return {
        "kind": "message",
        "id": str(message.id),
        "channel": {"id": str(channel_id), "name": getattr(channel, "name", None)},
        "guild": None if message.guild is None else _guild_ref(message.guild),
        "author": {"id": str(author.id), "name": author.display_name, "avatar_url": author.display_avatar.url},
        "content": message.content,
        "content_hidden": _content_hidden(bot, message),
        "created_at": _iso(message.created_at),
        "jump_url": message.jump_url,
        "embeds": [e.to_dict() for e in message.embeds],
        "attachments": [{"filename": a.filename, "url": a.url} for a in message.attachments],
    }


async def _lookup(bot: discord.Client, target: int, channel_id: int | None) -> dict[str, Any]:
    """在 bot 的事件迴圈上跑：逐一比對各種東西，對到幾種就回幾張。"""
    found = [
        None if channel_id is None else await _lookup_message(bot, target, channel_id),
        await _lookup_user(bot, target),
        _lookup_channel(bot, target),
        _lookup_guild(bot, target),
        _lookup_role(bot, target),
    ]
    return {
        "id": str(target),
        "created_at": discord.utils.snowflake_time(target).isoformat(),
        "member_cache_complete": all(g.chunked for g in bot.guilds),
        "matches": [m for m in found if m is not None],
    }


@router.get("/lookup")
async def lookup(id: str = "", channel_id: str = "", _: SessionInfo = Depends(require_bot_owner)):
    """錯誤：400 invalid_id（id 或 channel_id 不是 1 到 2^64-1 的整數）；503 bot_unavailable。"""
    target = _parse_id(id)
    channel = _parse_id(channel_id) if channel_id else None
    bot = sclient.bot
    if bot is None or not bot.is_ready():
        raise DashboardError(503, "bot_unavailable")
    return await asyncio.wrap_future(bot.submit(_lookup(bot, target, channel)))
