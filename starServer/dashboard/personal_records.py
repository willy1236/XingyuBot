"""個人區的紀錄：語音時數、警告、投票、賭盤與抽獎（T-06）。

GET /dashboard/personal/records/voice?discord_id=                          各伺服器的語音分鐘數與名次，由多到少
GET /dashboard/personal/records/{warnings|polls|bets|giveaways}?discord_id=&offset=&limit=   由新到舊，回 {items, total}

`discord_id` 必須在個人區可見範圍內。紀錄以資料庫為準，Discord 只用來補伺服器名稱，bot 已離開的伺服器名稱為 null。
"""

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query

from starDiscord.cmds import task as voice_task
from starlib import sclient, sqldb
from starlib.database import WarningType

from .db import run_db
from .errors import DashboardError
from .personal import PersonalScope, require_personal
from .voice_ranking import is_member, minutes, ranking

router = APIRouter(prefix="/dashboard")

PAGE_SIZE = 20

_WARNING_KEYS = {
    WarningType.Warning: "warning",
    WarningType.Timeout: "timeout",
    WarningType.Kick: "kick",
    WarningType.Ban: "ban",
}
_BET_SIDES = {1: "blue_title", 2: "pink_title"}


def _check_scope(discord_id: int, scope: PersonalScope) -> None:
    if discord_id not in scope.discord_ids:
        raise DashboardError(403, "no_permission")


async def _guild_names(guild_ids: set[int]) -> dict[int, str | None]:
    """bot 所在伺服器的名稱；已離開的伺服器為 None。bot 尚未 ready 時回 503，避免把暫時狀態誤判成已離開。"""
    if not guild_ids:
        return {}
    bot = sclient.bot
    if bot is None or not bot.is_ready():
        raise DashboardError(503, "bot_unavailable")

    async def _names() -> dict[int, str | None]:
        result = {}
        for gid in guild_ids:
            guild = bot.get_guild(gid)
            result[gid] = None if guild is None else guild.name
        return result

    return await asyncio.wrap_future(bot.submit(_names()))


def _iso(value: datetime | None) -> str | None:
    """舊版 /bet place 寫入的下注沒有時間（NULL）。"""
    return None if value is None else value.isoformat()


# ====== voice ======
def _voice_items(discord_id: int, saved: list[tuple[int, timedelta]], scope: PersonalScope) -> list[dict]:
    """各伺服器的時數與名次，在 bot 的事件迴圈上呼叫（見 voice_ranking）。

    bot 還在的伺服器：時數含尚未存檔的分鐘，附名次與排行人數，ranking_visible 表示可以開排行頁。
    bot 已離開的伺服器：只有資料庫的時數，名稱、名次與人數為 null。
    """
    bot = sclient.bot
    saved_totals = dict(saved)
    guild_ids = set(saved_totals) | {gid for gid, users in voice_task.voice_times.items() if discord_id in users}
    items = []
    for gid in guild_ids:
        guild = bot.get_guild(gid)
        item = {"guild_id": str(gid), "guild_name": None, "rank": None, "ranked": None, "ranking_visible": False}
        if guild is None:
            item["minutes"] = minutes(saved_totals[gid])
        else:
            ranked = ranking(gid)
            rank, total = next((i, t) for i, (uid, t) in enumerate(ranked) if uid == discord_id)
            item |= {
                "guild_name": guild.name,
                "minutes": minutes(total),
                "rank": rank + 1,
                "ranked": len(ranked),
                "ranking_visible": is_member(guild, scope.discord_ids),
            }
        items.append(item)
    return sorted(items, key=lambda i: (-i["minutes"], int(i["guild_id"])))


@router.get("/personal/records/voice")
async def voice_records(discord_id: int, scope: PersonalScope = Depends(require_personal())):
    _check_scope(discord_id, scope)
    saved = await run_db(lambda: [(v.guild_id, v.total_minute) for v in sqldb.list_voice_times(discord_id)])
    bot = sclient.bot
    if bot is None or not bot.is_ready():
        # bot 沒在跑時也沒有尚未存檔的分鐘，沒有紀錄就不需要 bot
        if not saved:
            return {"items": []}
        raise DashboardError(503, "bot_unavailable")

    async def _read() -> list[dict]:
        return _voice_items(discord_id, saved, scope)

    return {"items": await asyncio.wrap_future(bot.submit(_read()))}


# ====== 分頁類 ======
# 各類回傳 (已轉成純資料的列, 總數)；列裡的 guild_id 在 paged_records 換成伺服器名稱。
_Page = tuple[list[dict], int]


def _warnings(discord_id: int, offset: int, limit: int) -> _Page:
    rows, total = sqldb.list_user_warnings(discord_id, offset, limit)
    return [
        {
            "id": w.warning_id,
            "guild_id": w.create_guild,
            "type": _WARNING_KEYS.get(WarningType(w.moderate_type), "warning"),
            "at": _iso(w.create_time),
            "reason": w.reason,
            "duration_seconds": None if w.last_time is None else int(w.last_time.total_seconds()),
        }
        for w in rows
    ], total


def _polls(discord_id: int, offset: int, limit: int) -> _Page:
    rows, total = sqldb.list_user_polls(discord_id, offset, limit)
    return [
        {
            "id": poll_id,
            "guild_id": None if poll is None else poll.guild_id,
            "title": None if poll is None else poll.title,
            "options": options,
            "at": _iso(at),
        }
        for poll, poll_id, at, options in rows
    ], total


def _bets(discord_id: int, offset: int, limit: int) -> _Page:
    rows, total = sqldb.list_user_bets(discord_id, offset, limit)
    return [
        {
            "id": user_bet.bet_id,
            "title": None if bet is None else bet.title,
            "option": None if bet is None else getattr(bet, _BET_SIDES.get(user_bet.bet_option, ""), None),
            "amount": user_bet.bet_amount,
            "at": _iso(user_bet.bet_at),
        }
        for user_bet, bet in rows
    ], total


def _giveaways(discord_id: int, offset: int, limit: int) -> _Page:
    rows, total = sqldb.list_user_giveaways(discord_id, offset, limit)
    return [
        {
            "id": entry.giveaway_id,
            "guild_id": None if giveaway is None else giveaway.guild_id,
            "prize": None if giveaway is None else giveaway.prize_name,
            "result": "deleted"
            if giveaway is None
            else "pending"
            if giveaway.is_on
            else ("won" if entry.is_winner else "lost"),
            "at": _iso(entry.join_at),
        }
        for entry, giveaway in rows
    ], total


_KINDS: dict[str, Callable[[int, int, int], _Page]] = {
    "warnings": _warnings,
    "polls": _polls,
    "bets": _bets,
    "giveaways": _giveaways,
}


@router.get("/personal/records/{kind}")
async def paged_records(
    kind: Literal["warnings", "polls", "bets", "giveaways"],
    discord_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(PAGE_SIZE, ge=1, le=PAGE_SIZE),
    scope: PersonalScope = Depends(require_personal()),
):
    _check_scope(discord_id, scope)
    items, total = await run_db(lambda: _KINDS[kind](discord_id, offset, limit))
    if any("guild_id" in item for item in items):
        names = await _guild_names({i["guild_id"] for i in items if i["guild_id"] is not None})
        for item in items:
            gid = item.pop("guild_id")
            item["guild_name"] = None if gid is None else names.get(gid)
    return {"items": items, "total": total}
