"""bot owner 營運入口的系統部分：各 process 與服務的運行狀態。

GET /dashboard/ops/system/status  Discord bot、Twitch bot、訊息匯流排、後台 DB 的狀態

每一區都是 {"state": "up"|"down"|"error", ...}：down 是確定沒在跑，error 是取資料時出錯；匯流排另有 unconfigured。
每一區各自取值，一區出錯不影響其他區。狀態端點不經 `run_db`，DB executor 塞住時也要能回應。
權限同 `ops.py`：只放行 bot owner，不是回 403 not_bot_owner。
"""

import asyncio
import inspect
import logging
import math
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Depends

from starlib import sclient
from starlib.messaging import get_bus

from . import db, twitch_control
from .ops import require_bot_owner
from .session import SessionInfo
from .twitch_control import BotOffline

log = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard/ops/system")

DOWN: dict[str, Any] = {"state": "down"}
ERROR: dict[str, Any] = {"state": "error"}


def _discord() -> dict[str, Any]:
    bot = sclient.bot
    if bot is None:
        return DOWN
    latency = bot.latency
    guilds = list(bot.guilds)
    return {
        "state": "up",
        "ready": bot.is_ready(),
        "latency_ms": None if not math.isfinite(latency) else round(latency * 1000),
        "started_at": None if bot.started_at is None else bot.started_at.isoformat(),
        "guild_count": len(guilds),
        "unchunked_guilds": sum(not g.chunked for g in guilds),
    }


async def _twitch() -> dict[str, Any]:
    status = await twitch_control.bot_status()
    if isinstance(status, BotOffline):
        return DOWN
    return {"state": "up", "started_at": status.started_at, "rooms": status.rooms}


def _bus() -> dict[str, Any]:
    return {"state": get_bus().state}


def _db() -> dict[str, Any]:
    return {"state": "up", "executor": db.executor_stats(), "pool": db.pool_stats()}


type Section = dict[str, Any]


async def _section(name: str, get: Callable[[], Section | Awaitable[Section]]) -> Section:
    try:
        result = get()
        return await result if inspect.isawaitable(result) else result
    except Exception:
        log.exception("取得系統狀態的 %s 區失敗", name)
        return ERROR


@router.get("/status")
async def status(_: SessionInfo = Depends(require_bot_owner)):
    discord, twitch, bus, database = await asyncio.gather(
        _section("discord", _discord),
        _section("twitch", _twitch),
        _section("bus", _bus),
        _section("db", _db),
    )
    return {"discord": discord, "twitch": twitch, "bus": bus, "db": database}
