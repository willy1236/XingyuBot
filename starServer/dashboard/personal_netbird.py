"""個人區的 NetBird 節點與安裝指令（T-09）。"""

import logging

from fastapi import APIRouter, Depends

from starlib.exceptions import APINetworkError
from starlib.netbird_setup import create_setup, list_peers

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
    try:
        peers = await run_db(lambda: list_peers(user_id))
    except APINetworkError:
        log.exception("NetBird query failed")
        raise DashboardError(502, "netbird_unavailable")
    if peers is not None:
        result["bound"] = True
        result["peers"] = [_peer(p) for p in peers]
    return result


@router.post("/personal/netbird/setup")
async def setup_netbird(scope: PersonalScope = Depends(require_personal(write=True))):
    """按下才產生；setup key 只出現在這次回應。"""
    user_id = scope.tool_user_id
    assert user_id is not None  # tools_writable 時 tool_user_id 一定是 account_id
    try:
        setup = await run_db(lambda: create_setup(user_id))
    except APINetworkError:
        log.exception("NetBird setup failed")
        raise DashboardError(502, "netbird_unavailable")
    return {"command": setup.command, "bat": setup.bat}
