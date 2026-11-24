"""實況主後台：實況資訊（標題、分類），實況主與 mod 都能用。用實況主 token 直接打 Helix，不經 Twitch bot。

GET /dashboard/channels/{id}/stream-info                 {title, category_id, category_name, is_live, started_at, can_edit}
GET /dashboard/channels/{id}/stream-info/categories?q=   {categories: [{id, name}]}
PUT /dashboard/channels/{id}/stream-info                 body {title, category_id}；沒有 channel:manage:broadcast 回 409 scope_missing
Twitch 出錯回 502 twitch_failed。
"""

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from starlib import twitch_stream_info, twitch_tokens
from starlib.twitch_tokens import TokenInvalid

from . import twitch_control
from .channels import ChannelAccess, require_channel, require_enabled_channel
from .db import run_db
from .errors import DashboardError

log = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard")
HELIX = "https://api.twitch.tv/helix"
#: Helix `PATCH /channels` 的標題長度上限
TITLE_MAX = 140


class StreamInfoBody(BaseModel):
    title: str = Field(min_length=1, max_length=TITLE_MAX)
    category_id: str = Field(pattern=r"^\d{1,20}$")


async def _credentials(twitch_id: int) -> dict[str, str]:
    credentials = await twitch_control.broadcaster_credentials(twitch_id)
    if isinstance(credentials, TokenInvalid):
        if credentials.reason == "unavailable":
            raise DashboardError(502, "twitch_failed")
        raise DashboardError(409, "scope_missing")
    token, client_id = credentials
    return {"Authorization": f"Bearer {token}", "Client-Id": client_id}


async def _helix(method: str, path: str, headers: dict[str, str], **kwargs: Any) -> dict:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.request(method, f"{HELIX}{path}", headers=headers, **kwargs)
        response.raise_for_status()
        return response.json() if response.content else {}
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("Twitch %s %s 失敗：%s", method, path, type(exc).__name__)
        raise DashboardError(502, "twitch_failed") from None


async def _channel(twitch_id: int, headers: dict[str, str]) -> dict[str, str]:
    data = (await _helix("GET", "/channels", headers, params={"broadcaster_id": str(twitch_id)}))["data"]
    if not data:
        raise DashboardError(502, "twitch_failed")
    return {"title": data[0]["title"], "game_id": data[0]["game_id"], "game": data[0]["game_name"]}


@router.get("/channels/{twitch_id}/stream-info")
async def get_stream_info(twitch_id: int, _access: ChannelAccess = Depends(require_channel)):
    headers = await _credentials(twitch_id)
    channel = await _channel(twitch_id, headers)
    streams = (await _helix("GET", "/streams", headers, params={"user_id": str(twitch_id)}))["data"]
    can_edit = await run_db(lambda: twitch_tokens.stream_info_granted(twitch_id))
    return {
        "title": channel["title"],
        "category_id": channel["game_id"],
        "category_name": channel["game"],
        "is_live": bool(streams),
        "started_at": streams[0]["started_at"] if streams else None,
        "can_edit": can_edit,
    }


@router.get("/channels/{twitch_id}/stream-info/categories")
async def search_categories(
    twitch_id: int, q: str = Query(min_length=1, max_length=100), _access: ChannelAccess = Depends(require_channel)
):
    headers = await _credentials(twitch_id)
    found = (await _helix("GET", "/search/categories", headers, params={"query": q, "first": 20}))["data"]
    return {"categories": [{"id": item["id"], "name": item["name"]} for item in found]}


@router.put("/channels/{twitch_id}/stream-info", status_code=204)
async def update_stream_info(
    twitch_id: int, body: StreamInfoBody, access: ChannelAccess = Depends(require_enabled_channel)
) -> None:
    if not await run_db(lambda: twitch_tokens.stream_info_granted(twitch_id)):
        raise DashboardError(409, "scope_missing")
    headers = await _credentials(twitch_id)
    title = body.title.strip()
    before = await _channel(twitch_id, headers)
    changes: dict[str, str] = {}
    if title != before["title"]:
        changes["title"] = title
    if body.category_id != before["game_id"]:
        changes["game_id"] = body.category_id
    if not changes:
        return
    await _helix("PATCH", "/channels", headers, params={"broadcaster_id": str(twitch_id)}, json=changes)
    after = await _channel(twitch_id, headers)
    await run_db(lambda: twitch_stream_info.record_updated(twitch_id, access.actor, before, after))
