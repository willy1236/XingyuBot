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
from pydantic import BaseModel, Field, model_validator

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
    title: str | None = Field(default=None, max_length=TITLE_MAX)
    category_id: str | None = Field(default=None, pattern=r"^(?:[0-9]{1,20})?$")

    @model_validator(mode="after")
    def require_changes(self):
        if not self.model_fields_set or any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("至少提供標題或分類")
        return self


async def _credentials(twitch_id: int, *, require_write_scope: bool = False) -> dict[str, str]:
    credentials = await twitch_control.broadcaster_credentials(twitch_id)
    if isinstance(credentials, TokenInvalid):
        if credentials.reason == "unavailable":
            raise DashboardError(502, "twitch_failed")
        raise DashboardError(409, "scope_missing")
    token, client_id = credentials
    if require_write_scope and not await run_db(lambda: twitch_tokens.stream_info_granted(twitch_id)):
        raise DashboardError(409, "scope_missing")
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
    headers = await _credentials(twitch_id, require_write_scope=True)
    before = await _channel(twitch_id, headers)
    changes: dict[str, str] = {}
    category_name = before["game"]
    title = body.title.strip() if body.title is not None else None
    if title is not None and body.title != before["title"] and title != before["title"]:
        if not title:
            raise DashboardError(400, "invalid_request")
        changes["title"] = title
    if body.category_id is not None and body.category_id != before["game_id"]:
        if not body.category_id:
            raise DashboardError(400, "invalid_request")
        categories = (await _helix("GET", "/games", headers, params={"id": body.category_id}))["data"]
        if not categories:
            raise DashboardError(400, "invalid_request")
        category_name = categories[0]["name"]
        changes["game_id"] = body.category_id
    if not changes:
        return
    await _helix("PATCH", "/channels", headers, params={"broadcaster_id": str(twitch_id)}, json=changes)
    twitch_control.invalidate("twitch_stream_info", twitch_id)
    after = {**before, **changes, "game": category_name}
    await run_db(lambda: twitch_stream_info.record_updated(twitch_id, access.actor, before, after))
