"""實況主後台：聊天室執法紀錄與誤判處置，實況主與 mod 都能用。

GET  /dashboard/channels/{id}/enforcement?offset=                30 天內的執法紀錄（新的在前，每頁 50 筆）
POST /dashboard/channels/{id}/enforcement/{log_id}/lift          解除處罰；回 {result: "lifted" | "not_punished"}
POST /dashboard/channels/{id}/enforcement/{log_id}/clear-strikes 清除該觀眾所有過濾器的犯規次數
POST /dashboard/channels/{id}/enforcement/{log_id}/regular       把該觀眾加入常客
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from starlib import sqldb, twitch_enforcement, twitch_regulars
from starlib.database import TwitchEnforcementLog
from starlib.messaging import rpc

from . import twitch_control
from .channels import ChannelAccess, require_channel, require_enabled_channel
from .db import run_db
from .errors import DashboardError

router = APIRouter(prefix="/dashboard")

LogId = Annotated[int, Path(ge=1, le=2**63 - 1)]


def entry_json(row: TwitchEnforcementLog) -> dict:
    """後台與營運入口共用的紀錄形狀。"""
    return {
        "id": row.id,
        "at": row.at.isoformat(),
        "user_id": str(row.user_id),
        "user_login": row.user_login,
        "user_name": row.user_name,
        "filter": row.filter,
        "strike": row.strike,
        "action": row.action,
        "duration": row.duration,
        "message": row.message,
        "status": row.status,
        "lifted_at": None if row.lifted_at is None else row.lifted_at.isoformat(),
    }


def page_json(rows: list[TwitchEnforcementLog]) -> dict:
    """列表端點的回應：這一頁的紀錄與有沒有下一頁。"""
    return {"entries": [entry_json(row) for row in rows], "has_next": len(rows) == twitch_enforcement.PAGE_SIZE}


async def _call(method: str, twitch_id: int, user_id: int) -> dict:
    """呼叫 Twitch bot；離線回 503 bot_offline，bot 內部或 Twitch 出錯回 502 twitch_failed（可重試）。"""
    try:
        result = await twitch_control._call(method, {"twitch_id": twitch_id, "user_id": user_id})
    except rpc.RpcHandlerError:
        raise DashboardError(502, "twitch_failed") from None
    if isinstance(result, twitch_control.BotOffline):
        raise DashboardError(503, "bot_offline")
    return result


async def _find(twitch_id: int, log_id: int) -> TwitchEnforcementLog:
    row = await run_db(lambda: twitch_enforcement.get(twitch_id, log_id))
    if row is None:
        raise DashboardError(404, "enforcement_not_found")
    return row


@router.get("/channels/{twitch_id}/enforcement")
async def list_enforcement(
    twitch_id: int, offset: Annotated[int, Query(ge=0)] = 0, _access: ChannelAccess = Depends(require_channel)
):
    return await run_db(lambda: page_json(twitch_enforcement.list_page(sqldb.session, twitch_id, offset)))


@router.post("/channels/{twitch_id}/enforcement/{log_id}/lift")
async def lift(twitch_id: int, log_id: LogId, access: ChannelAccess = Depends(require_enabled_channel)):
    row = await _find(twitch_id, log_id)
    if row.action not in ("timeout", "ban"):
        raise DashboardError(400, "not_liftable")
    if not twitch_enforcement.is_active_punishment(row):
        return {"result": "not_punished"}
    result = (await _call("moderation.lift", twitch_id, row.user_id))["result"]
    if result == "not_mod":
        raise DashboardError(409, "bot_not_mod")
    if result == "lifted":
        await run_db(lambda: twitch_enforcement.mark_lifted(twitch_id, log_id, access.actor))
    return {"result": result}


@router.post("/channels/{twitch_id}/enforcement/{log_id}/clear-strikes", status_code=204)
async def clear_strikes(
    twitch_id: int, log_id: LogId, access: ChannelAccess = Depends(require_enabled_channel)
) -> None:
    row = await _find(twitch_id, log_id)
    await _call("moderation.clear_strikes", twitch_id, row.user_id)
    await run_db(
        lambda: twitch_enforcement.record_clear_strikes(twitch_id, log_id, access.actor, row.user_id, row.user_login)
    )


@router.post("/channels/{twitch_id}/enforcement/{log_id}/regular", status_code=204)
async def add_regular(twitch_id: int, log_id: LogId, access: ChannelAccess = Depends(require_enabled_channel)) -> None:
    row = await _find(twitch_id, log_id)
    added = await run_db(
        lambda: twitch_regulars.add(twitch_id, access.actor, "dashboard", row.user_id, row.user_login, row.user_name)
    )
    if not added:
        raise DashboardError(409, "already_regular")
