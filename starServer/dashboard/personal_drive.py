"""個人區的雲端資料夾共用設定（T-08）。"""

import asyncio
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from starlib import sclient, sqldb
from starlib.drive_share import normalize_gmail, plan_share, request_remove, request_share, save_share
from starlib.instance import drive_share_guilds

from .db import run_db
from .errors import DashboardError
from .personal import PersonalScope, require_personal

log = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard")


class DriveBody(BaseModel):
    gmail: str


def _has_member(discord_ids: list[int]) -> bool:
    """可見的 Discord 中，是否有任一個在開放共用的伺服器裡（須在 bot 的事件迴圈上呼叫）。"""
    bot = sclient.bot
    for guild_id in drive_share_guilds:
        guild = bot.get_guild(guild_id)
        if guild is not None and any(guild.get_member(i) is not None for i in discord_ids):
            return True
    return False


async def _eligible(scope: PersonalScope) -> bool:
    bot = sclient.bot
    if bot is None or not bot.is_ready():
        raise DashboardError(503, "bot_unavailable")

    async def _check() -> bool:
        return _has_member(scope.discord_ids)

    return await asyncio.wrap_future(bot.submit(_check()))


async def _state(scope: PersonalScope) -> dict:
    gmail = None
    if scope.tool_user_id is not None:
        user_id = scope.tool_user_id
        share = await run_db(lambda: sqldb.get_drive_share(user_id))
        gmail = share.gmail if share else None
    return {"writable": scope.tools_writable, "unavailable": scope.tool_unavailable, "eligible": True, "gmail": gmail}


async def _require_eligible(scope: PersonalScope) -> None:
    if not await _eligible(scope):
        raise DashboardError(403, "not_eligible")


@router.get("/personal/drive")
async def get_drive(scope: PersonalScope = Depends(require_personal())):
    if not await _eligible(scope):
        return {
            "writable": scope.tools_writable,
            "unavailable": scope.tool_unavailable,
            "eligible": False,
            "gmail": None,
        }
    return await _state(scope)


@router.put("/personal/drive")
async def put_drive(body: DriveBody, scope: PersonalScope = Depends(require_personal(write=True))):
    await _require_eligible(scope)
    gmail = normalize_gmail(body.gmail)
    if gmail is None:
        raise DashboardError(400, "invalid_gmail")
    user_id = scope.tool_user_id
    try:
        plan = await run_db(lambda: plan_share(user_id))
        # Google 的 HTTP 在 DB executor 外執行，全部成功後才寫入
        share_id = await asyncio.to_thread(request_share, plan, gmail)
        await run_db(lambda: save_share(user_id, gmail, share_id))
    except Exception:
        log.exception("Drive share failed")
        raise DashboardError(502, "drive_failed") from None
    return await _state(scope)


@router.delete("/personal/drive")
async def delete_drive(scope: PersonalScope = Depends(require_personal(write=True))):
    await _require_eligible(scope)
    user_id = scope.tool_user_id
    try:
        plan = await run_db(lambda: plan_share(user_id))
        await asyncio.to_thread(request_remove, plan)
        if plan.old_share_id is not None:
            await run_db(lambda: sqldb.remove_drive_share(user_id))
    except Exception:
        log.exception("Drive unshare failed")
        raise DashboardError(502, "drive_failed") from None
    return await _state(scope)
