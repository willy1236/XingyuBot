"""個人區的 NetBird 節點與安裝指令（T-09）。"""

import asyncio
import logging

from fastapi import APIRouter, Depends

from starlib.exceptions import APINetworkError
from starlib.netbird_setup import fetch_peers, plan_peers, plan_setup, request_setup_key, save_setup

from .db import run_db
from .errors import DashboardError
from .personal import PersonalScope, require_personal

log = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard")


def _peer(peer: dict) -> dict:
    return {
        "name": peer.get("name") or "未命名節點",
        "ip": peer.get("ip"),
        "connected": bool(peer.get("connected")),
        "last_seen": peer.get("last_seen") or None,
        "os": peer.get("os") or None,
        "version": peer.get("version") or None,
    }


@router.get("/personal/netbird")
async def get_netbird(scope: PersonalScope = Depends(require_personal())):
    """綁定與節點；頁面載入時只讀，不產生安裝指令。"""
    result = {"writable": scope.tools_writable, "unavailable": scope.tool_unavailable, "bound": False, "peers": []}
    if scope.tool_user_id is None:
        return result
    user_id = scope.tool_user_id
    # DB 讀與 NetBird HTTP 分開：HTTP 等待期間不佔 DB 連線與 dashboard executor
    query = await run_db(lambda: plan_peers(user_id))
    if query is None:
        return result
    try:
        peers = await asyncio.to_thread(fetch_peers, query)
    except APINetworkError:
        log.exception("NetBird query failed")
        raise DashboardError(502, "netbird_unavailable") from None
    result["bound"] = True
    result["peers"] = [_peer(p) for p in peers]
    return result


@router.post("/personal/netbird/setup")
async def setup_netbird(scope: PersonalScope = Depends(require_personal(write=True))):
    """按下才產生；setup key 只出現在這次回應。"""
    user_id = scope.tool_user_id
    if user_id is None:  # tools_writable 時 tool_user_id 一定是 account_id，防禦用
        raise DashboardError(403, "domalyze_required")
    plan = await run_db(lambda: plan_setup(user_id))
    try:
        key = await asyncio.to_thread(request_setup_key, plan)
    except APINetworkError:
        log.exception("NetBird setup failed")
        raise DashboardError(502, "netbird_unavailable") from None
    # NetBird 全部成功後才寫入綁定
    setup = await run_db(lambda: save_setup(user_id, key))
    return {"command": setup.command, "bat": setup.bat}
