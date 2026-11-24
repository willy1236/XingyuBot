"""實況主後台：Twitch Blocked Terms，實況主與 mod 都能用。詞存在 Twitch，經 Twitch bot 的 RPC 讀寫。

GET    /dashboard/channels/{id}/blocked-terms            目前的詞 {terms: [{id, text}]}
POST   /dashboard/channels/{id}/blocked-terms            新增，body {text}，回 {term: {id, text}}
DELETE /dashboard/channels/{id}/blocked-terms/{term_id} 刪除
bot 不是頻道 mod 回 409 bot_not_mod，bot 離線回 503 bot_offline，Twitch 出錯回 502 twitch_failed。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, Field

from starlib import twitch_blocked_terms
from starlib.messaging import rpc

from . import twitch_control
from .channels import ChannelAccess, require_channel, require_enabled_channel
from .db import run_db
from .errors import DashboardError

router = APIRouter(prefix="/dashboard")

TermId = Annotated[str, Path(min_length=1, max_length=128)]


class TermBody(BaseModel):
    text: str = Field(min_length=1, max_length=500)


async def _call(method: str, twitch_id: int, **payload: object) -> dict:
    try:
        result = await twitch_control._call(method, {"twitch_id": twitch_id, **payload})
    except rpc.RpcHandlerError:
        raise DashboardError(502, "twitch_failed") from None
    if isinstance(result, twitch_control.BotOffline):
        raise DashboardError(503, "bot_offline")
    if result.get("error") == "not_mod":
        raise DashboardError(409, "bot_not_mod")
    return result


@router.get("/channels/{twitch_id}/blocked-terms")
async def list_terms(twitch_id: int, _access: ChannelAccess = Depends(require_channel)):
    return await _call("blocked_terms.list", twitch_id)


@router.post("/channels/{twitch_id}/blocked-terms")
async def add_term(twitch_id: int, body: TermBody, access: ChannelAccess = Depends(require_enabled_channel)):
    text = body.text.strip()
    if len(text) < 2:
        raise DashboardError(422, "invalid_term")
    result = await _call("blocked_terms.add", twitch_id, text=text)
    term = result["term"]
    await run_db(lambda: twitch_blocked_terms.record_added(twitch_id, access.actor, term["id"], term["text"]))
    return {"term": term}


@router.delete("/channels/{twitch_id}/blocked-terms/{term_id}", status_code=204)
async def remove_term(
    twitch_id: int, term_id: TermId, access: ChannelAccess = Depends(require_enabled_channel)
) -> None:
    listed = (await _call("blocked_terms.list", twitch_id))["terms"]
    text = next((term["text"] for term in listed if term["id"] == term_id), None)
    await _call("blocked_terms.remove", twitch_id, term_id=term_id)
    await run_db(lambda: twitch_blocked_terms.record_removed(twitch_id, access.actor, term_id, text))
