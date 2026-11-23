"""實況主後台的常客名單。管理者以 Twitch login 新增，以固定的使用者 ID 移除。"""

import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, Field

from starlib import twitch_regulars
from starlib.twitch_tokens import TokenInvalid

from . import twitch_control
from .channels import ChannelAccess, require_channel, require_enabled_channel
from .db import run_db
from .errors import DashboardError

log = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard")
USERS_URL = "https://api.twitch.tv/helix/users"


class RegularBody(BaseModel):
    login: str = Field(max_length=128)


async def _find_user(twitch_id: int, login: str) -> tuple[int, str, str]:
    credentials = await twitch_control.broadcaster_credentials(twitch_id)
    if isinstance(credentials, TokenInvalid):
        raise DashboardError(503, "user_lookup_unavailable")
    token, client_id = credentials
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                USERS_URL,
                params={"login": login},
                headers={"Authorization": f"Bearer {token}", "Client-Id": client_id},
            )
        response.raise_for_status()
        users = response.json()["data"]
        if not isinstance(users, list):
            raise ValueError("invalid Helix users response")
        if not users:
            raise DashboardError(404, "user_not_found")
        user = users[0]
        return int(user["id"]), user["login"], user["display_name"]
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        log.warning("查詢頻道 %s 的 Twitch 觀眾失敗：%s", twitch_id, type(exc).__name__)
        raise DashboardError(503, "user_lookup_unavailable") from None


@router.get("/channels/{twitch_id}/regulars")
async def list_regulars(twitch_id: int, _access: ChannelAccess = Depends(require_channel)):
    regulars = await run_db(
        lambda: [
            {
                "user_id": str(row.user_id),
                "user_login": row.user_login,
                "user_name": row.user_name,
                "created_at": row.created_at.isoformat(),
            }
            for row in twitch_regulars.list_regulars(twitch_id)
        ]
    )
    return {"regulars": regulars}


@router.post("/channels/{twitch_id}/regulars", status_code=204)
async def add_regular(
    twitch_id: int,
    body: RegularBody,
    access: ChannelAccess = Depends(require_enabled_channel),
) -> None:
    login = body.login.strip().removeprefix("@").lower()
    if not login:
        raise DashboardError(404, "user_not_found")
    user_id, user_login, user_name = await _find_user(twitch_id, login)
    if not await run_db(
        lambda: twitch_regulars.add(
            twitch_id,
            access.actor,
            "dashboard",
            user_id,
            user_login,
            user_name,
        )
    ):
        raise DashboardError(409, "already_regular")


@router.delete("/channels/{twitch_id}/regulars/{user_id}", status_code=204)
async def remove_regular(
    twitch_id: int,
    user_id: Annotated[int, Path(ge=1, le=2**63 - 1)],
    access: ChannelAccess = Depends(require_enabled_channel),
) -> None:
    await run_db(lambda: twitch_regulars.remove(twitch_id, access.actor, "dashboard", user_id))
