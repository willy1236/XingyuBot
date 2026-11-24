"""bot owner 的營運入口：頻道清單、停權與解除停權、修改紀錄。

GET  /dashboard/ops/channels?page=&token_problem=
                                              所有曾經出現過的頻道（每頁 50 筆），只回 DB 狀態，停權的 state 是 banned；
                                              附已啟用頻道的 token 問題統計，token_problem=1 時只列 token 有問題的已啟用頻道
GET  /dashboard/ops/channels/{id}/health      單一頻道的完整判定（channel_health），前端逐列補查 partial 與原因
POST /dashboard/ops/channels/{id}/ban         停權：設 banned_at、state=disabled，bot 離開，並記修改紀錄
POST /dashboard/ops/channels/{id}/unban       解除停權：回到 disabled，不自動啟用，並記修改紀錄
GET  /dashboard/ops/channels/{id}/audit?page= 頻道的修改紀錄（新的在前，每頁 50 筆）
GET  /dashboard/ops/channels/{id}/enforcement?offset= 頻道 30 天內的執法紀錄（新的在前，每頁 50 筆）

所有端點都要求 bot owner；不是（含沒有 Discord 身分）回 403 not_bot_owner。
這個代碼不能用 no_permission 或 discord_required：前端在全域把它們當成伺服器權限與 Discord 登入處理並整頁導走。
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from starlib import sqldb, twitch_audit, twitch_enforcement
from starlib.database import OAuthToken, TwitchBotJoinChannel
from starlib.twitch_tokens import missing_scopes, token_state
from starlib.utils import nowtz

from . import channel_enforcement, twitch_control
from .auth import is_bot_owner
from .channel_activation import _sync_bot
from .channel_health import channel_health, is_banned
from .channels import BANNED_STATE
from .db import run_db
from .errors import DashboardError
from .session import SessionInfo, audit_actor, require_any_session

log = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard/ops")

PAGE_SIZE = 50
REASON_MAX = 500


async def require_bot_owner(info: SessionInfo = Depends(require_any_session)) -> SessionInfo:
    """營運端點的 dependency：只放行 bot owner。

    Raises:
        DashboardError: 401 session_expired；403 not_bot_owner（不是 owner，或沒有 Discord 身分）。
    """
    if not await is_bot_owner(info):
        raise DashboardError(403, "not_bot_owner")
    return info


def _offset(page: int) -> int:
    return (max(page, 1) - 1) * PAGE_SIZE


def _state(row: TwitchBotJoinChannel) -> str:
    return BANNED_STATE if is_banned(row) else row.state


def _channel_json(row: TwitchBotJoinChannel) -> dict[str, Any]:
    return {
        "id": str(row.twitch_id),
        "login": row.login,
        "name": row.display_name or row.login or str(row.twitch_id),
        "avatar_url": row.avatar_url,
        "state": _state(row),
        "banned_at": None if row.banned_at is None else row.banned_at.isoformat(),
        "banned_reason": row.banned_reason,
        "first_seen_at": None if row.first_seen_at is None else row.first_seen_at.isoformat(),
    }


def _get_row(twitch_id: int) -> TwitchBotJoinChannel:
    row = sqldb.get(TwitchBotJoinChannel, (twitch_id,))
    if row is None:
        raise DashboardError(404, "channel_not_found")
    return row


def _token_json(token: OAuthToken | None) -> dict[str, Any]:
    state = token_state(token)
    return {"state": state, "missing_scopes": missing_scopes(token) if state == "scope_missing" else []}


@router.get("/channels")
async def list_channels(page: int = 1, token_problem: bool = False, _: SessionInfo = Depends(require_bot_owner)):
    """統計與篩選只看 DB（`token_state`），不對 Twitch 發請求；統計本來就要全量撈，帶上每列 token 也用同一份結果。"""

    def load() -> dict[str, Any]:
        enabled = sqldb.list_enabled_channel_tokens()
        tokens = {channel.twitch_id: token for channel, token in enabled}
        states = {twitch_id: token_state(token) for twitch_id, token in tokens.items()}
        problems = {
            key: sum(state == key for state in states.values()) for key in ("missing", "scope_missing", "revoked")
        }
        if token_problem:
            # list_enabled_channel_tokens 已依清單的排序；篩完在 Python 分頁
            matched = [channel for channel, _ in enabled if states[channel.twitch_id] != "ok"]
            rows, total = matched[_offset(page) : _offset(page) + PAGE_SIZE], len(matched)
        else:
            rows, total = sqldb.list_twitch_join_channels(_offset(page), PAGE_SIZE)

        def row_json(row: TwitchBotJoinChannel) -> dict[str, Any]:
            data = _channel_json(row)
            if data["state"] == "enabled" and row.twitch_id in tokens:
                data["token"] = _token_json(tokens[row.twitch_id])
            return data

        return {
            "channels": [row_json(row) for row in rows],
            "page": max(page, 1),
            "page_size": PAGE_SIZE,
            "total": total,
            "token_problems": problems,
            "enabled_count": len(enabled),
        }

    return await run_db(load)


@router.get("/channels/{twitch_id}/health")
async def get_health(twitch_id: int, _: SessionInfo = Depends(require_bot_owner)):
    await run_db(lambda: _get_row(twitch_id))
    return (await channel_health(twitch_id)).to_json()


class BanBody(BaseModel):
    reason: str = Field(default="", max_length=REASON_MAX)


def _ban_snapshot(row: TwitchBotJoinChannel) -> dict[str, Any]:
    return {
        "banned_at": None if row.banned_at is None else row.banned_at.isoformat(),
        "banned_reason": row.banned_reason,
        "state": row.state,
    }


def _ban(twitch_id: int, reason: str | None, actor: twitch_audit.AuditActor) -> dict[str, Any]:
    """同一個交易內改停權欄位並記修改紀錄；已經停權且理由相同時什麼都不寫。"""
    row = _get_row(twitch_id)
    before = _ban_snapshot(row)
    if is_banned(row) and row.banned_reason == reason and row.state == "disabled":
        return _channel_json(row)
    try:
        if not is_banned(row):
            row.banned_at = nowtz()
        row.banned_reason = reason
        row.state = "disabled"
        sqldb.session.add(row)
        twitch_audit.record_change(
            twitch_id, actor, "dashboard", "channel", "ban", "update", before, _ban_snapshot(row)
        )
        sqldb.commit()
    except Exception:
        sqldb.session.rollback()
        raise
    return _channel_json(row)


def _unban(twitch_id: int, actor: twitch_audit.AuditActor) -> dict[str, Any]:
    """清除停權並回到 disabled（刪除資料後的 inactive 也一律回 disabled）；沒有被停權回 409。"""
    row = _get_row(twitch_id)
    if not is_banned(row):
        raise DashboardError(409, "channel_not_banned")
    before = _ban_snapshot(row)
    try:
        row.banned_at = None
        row.banned_reason = None
        row.state = "disabled"
        sqldb.session.add(row)
        twitch_audit.record_change(
            twitch_id, actor, "dashboard", "channel", "unban", "update", before, _ban_snapshot(row)
        )
        sqldb.commit()
    except Exception:
        sqldb.session.rollback()
        raise
    return _channel_json(row)


@router.post("/channels/{twitch_id}/ban")
async def ban_channel(twitch_id: int, body: BanBody, info: SessionInfo = Depends(require_bot_owner)):
    """停權任何狀態的頻道。`reason` 去頭尾空白，空字串存 null。"""
    actor = audit_actor(info)
    reason = body.reason.strip() or None
    channel = await run_db(lambda: _ban(twitch_id, reason, actor))
    log.info("Dashboard ops ban: %s by %s", twitch_id, actor.id)
    # state 已是 disabled：bot 離開聊天室並退訂；離線時下次啟動依資料庫為準
    bot_offline = await _sync_bot(twitch_id)
    twitch_control.invalidate("twitch_channel", twitch_id)
    return {"channel": channel, "bot_offline": bot_offline}


@router.post("/channels/{twitch_id}/unban")
async def unban_channel(twitch_id: int, info: SessionInfo = Depends(require_bot_owner)):
    actor = audit_actor(info)
    channel = await run_db(lambda: _unban(twitch_id, actor))
    log.info("Dashboard ops unban: %s by %s", twitch_id, actor.id)
    twitch_control.invalidate("twitch_channel", twitch_id)
    return {"channel": channel}


@router.get("/channels/{twitch_id}/audit")
async def list_audit(twitch_id: int, page: int = 1, _: SessionInfo = Depends(require_bot_owner)):
    def load() -> dict[str, Any]:
        channel = _channel_json(_get_row(twitch_id))
        entries, current, has_next = twitch_audit.list_page(twitch_id, page)
        return {
            "channel": channel,
            "entries": [e.to_json() for e in entries],
            "page": current,
            "has_next": has_next,
        }

    return await run_db(load)


@router.get("/channels/{twitch_id}/enforcement")
async def list_enforcement(
    twitch_id: int, offset: Annotated[int, Query(ge=0)] = 0, _: SessionInfo = Depends(require_bot_owner)
):
    def load() -> dict[str, Any]:
        channel = _channel_json(_get_row(twitch_id))
        return {
            "channel": channel,
            **channel_enforcement.page_json(twitch_enforcement.list_page(sqldb.session, twitch_id, offset)),
        }

    return await run_db(load)
