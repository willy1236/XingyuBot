"""實況主後台：計時訊息的清單與維護。

GET    /dashboard/channels/{twitch_id}/timers             計時訊息清單
POST   /dashboard/channels/{twitch_id}/timers             新增，body 是計時訊息的欄位
PUT    /dashboard/channels/{twitch_id}/timers/{timer_id}  編輯，body `{values, original}`
DELETE /dashboard/channels/{twitch_id}/timers/{timer_id}  刪除，body `{original}`

`original` 是打開表單時看到的可編輯欄位；和資料庫目前的值不同時回 409 conflict（形狀同伺服器後台，欄位值是字串，
見 `twitch_timers.comparable`）。修改要求頻道已啟用（409 channel_not_enabled）；欄位不合法或超過每頻道 20 則的上限
回 400 invalid_field 附欄位與原因（上限的欄位是 limit）。
儲存訊息內容前先過頻道 AutoMod：擋下回 422 automod_blocked，無法檢查回 503 automod_unavailable，兩者都不儲存。
"""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from starlib import twitch_timers
from starlib.database import TwitchTimer
from starlib.twitch_timers import TimerFields, TimerInvalid, TimerMissing, Verify

from . import twitch_control
from .channels import ChannelAccess, require_channel, require_enabled_channel
from .conflict import check_conflict
from .db import run_db
from .errors import DashboardError

router = APIRouter(prefix="/dashboard")


class Values(BaseModel):
    message: str
    interval_minutes: int
    min_chat_lines: int = 0
    enabled: bool = True

    def fields(self) -> TimerFields:
        return TimerFields(self.message, self.interval_minutes, self.min_chat_lines, self.enabled)


class PutBody(BaseModel):
    values: Values
    original: Values


class DeleteBody(BaseModel):
    original: Values


def _json(row: TwitchTimer) -> dict[str, Any]:
    return {"id": row.id, **twitch_timers.snapshot(row), "updated_at": row.updated_at.isoformat()}


def _verifier(original: Values) -> Verify:
    """資料庫目前的值（或已被刪除）和打開表單時不同就 raise 409 conflict。"""
    expected = twitch_timers.comparable(original.model_dump())

    def verify(current: dict[str, str | None] | None) -> None:
        conflict = check_conflict(current, expected)
        if conflict is not None:
            raise conflict.to_error()

    return verify


def _translate[T](work: Callable[[], T]) -> Callable[[], T]:
    """在 DB worker thread 上執行時，把共用模組的錯誤轉成後台的錯誤回應。"""

    def run() -> T:
        try:
            return work()
        except TimerInvalid as e:
            raise DashboardError(400, "invalid_field", field=e.field, reason=e.reason) from None
        except TimerMissing:
            raise DashboardError(409, "conflict", deleted=True, current=None) from None

    return run


async def _check_automod(twitch_id: int, message: str) -> None:
    match await twitch_control.check_template(twitch_id, message):
        case "blocked":
            raise DashboardError(422, "automod_blocked")
        case "unavailable":
            raise DashboardError(503, "automod_unavailable")


def _validate(fields: TimerFields) -> None:
    """先擋掉格式與範圍的錯誤，再花 AutoMod 檢查的額度。"""
    try:
        twitch_timers.validate(fields)
    except TimerInvalid as e:
        raise DashboardError(400, "invalid_field", field=e.field, reason=e.reason) from None


@router.get("/channels/{twitch_id}/timers")
async def list_timers(twitch_id: int, _access: ChannelAccess = Depends(require_channel)):
    rows = await run_db(lambda: [_json(row) for row in twitch_timers.list_timers(twitch_id)])
    return {"timers": rows}


@router.post("/channels/{twitch_id}/timers")
async def create_timer(
    twitch_id: int,
    body: Values,
    access: ChannelAccess = Depends(require_enabled_channel),
):
    fields = body.fields()
    _validate(fields)
    await _check_automod(twitch_id, body.message)
    actor = access.actor
    row = await run_db(_translate(lambda: _json(twitch_timers.create(twitch_id, actor, fields))))
    return {"timer": row}


@router.put("/channels/{twitch_id}/timers/{timer_id}")
async def update_timer(
    twitch_id: int,
    timer_id: int,
    body: PutBody,
    access: ChannelAccess = Depends(require_enabled_channel),
):
    fields = body.values.fields()
    _validate(fields)
    # 只改開關、間隔等設定時不花 AutoMod 檢查的額度，AutoMod 暫時無法檢查時也能開關計時訊息
    if body.values.message != body.original.message:
        await _check_automod(twitch_id, body.values.message)
    actor = access.actor
    verify = _verifier(body.original)
    row = await run_db(_translate(lambda: _json(twitch_timers.update(twitch_id, actor, timer_id, fields, verify))))
    return {"timer": row}


@router.delete("/channels/{twitch_id}/timers/{timer_id}")
async def delete_timer(
    twitch_id: int,
    timer_id: int,
    body: DeleteBody,
    access: ChannelAccess = Depends(require_enabled_channel),
):
    actor = access.actor
    verify = _verifier(body.original)
    await run_db(_translate(lambda: twitch_timers.delete(twitch_id, actor, timer_id, verify)))
    return {"ok": True}
