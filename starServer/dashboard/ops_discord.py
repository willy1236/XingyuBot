"""bot owner 營運入口的 Discord 部分：目前所在的伺服器、每日人數，與加入離開紀錄。

GET /dashboard/ops/discord?days=        目前所在的伺服器與總數（bot 沒就緒時 live 是 null），以及最近 days 天的每日人數
GET /dashboard/ops/discord/events?page= 伺服器加入、離開紀錄（新的在前，每頁 50 筆）

權限同 `ops.py`：只放行 bot owner，不是回 403 not_bot_owner。
"""

from datetime import timedelta
from typing import Any

import discord
from fastapi import APIRouter, Depends

from starlib import sclient, sqldb
from starlib.utils import nowtz

from .db import run_db
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
