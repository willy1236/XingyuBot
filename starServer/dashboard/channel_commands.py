"""實況主後台：自訂指令的清單與維護。

GET    /dashboard/channels/{twitch_id}/commands         指令清單
POST   /dashboard/channels/{twitch_id}/commands         新增，body 是指令的欄位
PUT    /dashboard/channels/{twitch_id}/commands/{name}  編輯或改名，body `{values, original}`
DELETE /dashboard/channels/{twitch_id}/commands/{name}  刪除，body `{original}`

`original` 是打開表單時看到的可編輯欄位，不含使用次數與更新時間，聊天室觸發指令才不會造成假衝突；
和資料庫目前的值不同時回 409 conflict（形狀同伺服器後台，欄位值是字串，見 `twitch_commands.comparable`）。
修改要求頻道已啟用（409 channel_not_enabled）；名稱或別名重複等欄位問題回 400 invalid_field 附欄位與原因。
儲存回應內容前先過頻道 AutoMod：擋下回 422 automod_blocked，無法檢查回 503 automod_unavailable，兩者都不儲存。
"""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from starlib import twitch_commands
from starlib.database import TwitchChatCommand
from starlib.twitch_commands import CommandFields, CommandInvalid, CommandMissing, Verify

from . import twitch_control
from .channels import ChannelAccess, require_channel, require_enabled_channel
from .conflict import check_conflict
from .db import run_db
from .errors import DashboardError

router = APIRouter(prefix="/dashboard")


class Values(BaseModel):
    name: str
    response: str
    aliases: list[str] = Field(default_factory=list, max_length=50)
    enabled: bool = True
    global_cooldown: int = 30
    user_cooldown: int = 0
    permission: str = "everyone"

    def fields(self) -> CommandFields:
        return CommandFields(
            self.response, tuple(self.aliases), self.enabled, self.global_cooldown, self.user_cooldown, self.permission
        )


class PutBody(BaseModel):
    values: Values
    original: Values


class DeleteBody(BaseModel):
    original: Values


def _json(row: TwitchChatCommand) -> dict[str, Any]:
    return {
        **twitch_commands.snapshot(row),
        "use_count": row.use_count,
        "updated_at": row.updated_at.isoformat(),
    }


def _verifier(original: Values) -> Verify:
    """資料庫目前的值和打開表單時不同（或已被刪除）就 raise 409 conflict。"""
    expected = twitch_commands.comparable(original.model_dump())

    def verify(current: dict[str, str | None] | None) -> None:
        conflict = check_conflict(current, expected)
        if conflict is not None:
            raise conflict.to_error()

    return verify


def _translate[T](work: Callable[[], T]) -> Callable[[], T]:
    """在 DB worker thread 上執行時，把共用模組的驗證錯誤轉成後台的錯誤回應。"""

    def run() -> T:
        try:
            return work()
        except CommandInvalid as e:
            raise DashboardError(400, "invalid_field", field=e.field, reason=e.reason) from None
        except CommandMissing:
            raise DashboardError(409, "conflict", deleted=True, current=None) from None

    return run


async def _check_automod(twitch_id: int, response: str) -> None:
    match await twitch_control.check_template(twitch_id, response):
        case "blocked":
            raise DashboardError(422, "automod_blocked")
        case "unavailable":
            raise DashboardError(503, "automod_unavailable")


@router.get("/channels/{twitch_id}/commands")
async def list_commands(twitch_id: int, _access: ChannelAccess = Depends(require_channel)):
    rows = await run_db(lambda: [_json(row) for row in twitch_commands.list_commands(twitch_id)])
    return {"commands": rows}


@router.post("/channels/{twitch_id}/commands")
async def create_command(
    twitch_id: int,
    body: Values,
    access: ChannelAccess = Depends(require_enabled_channel),
):
    fields = body.fields()
    await run_db(_translate(lambda: twitch_commands.validate(twitch_id, body.name, fields)))
    await _check_automod(twitch_id, body.response)
    actor = access.actor
    row = await run_db(
        _translate(lambda: _json(twitch_commands.create(twitch_id, actor, "dashboard", body.name, fields)))
    )
    return {"command": row}


@router.put("/channels/{twitch_id}/commands/{name}")
async def update_command(
    twitch_id: int,
    name: str,
    body: PutBody,
    access: ChannelAccess = Depends(require_enabled_channel),
):
    fields = body.values.fields()
    await run_db(_translate(lambda: twitch_commands.validate(twitch_id, body.values.name, fields, current_name=name)))
    # 只改開關、冷卻等設定時不花 AutoMod 檢查的額度，AutoMod 暫時無法檢查時也能開關指令
    if body.values.response != body.original.response:
        await _check_automod(twitch_id, body.values.response)
    actor = access.actor
    verify = _verifier(body.original)
    row = await run_db(
        _translate(
            lambda: _json(twitch_commands.update(twitch_id, actor, "dashboard", name, body.values.name, fields, verify))
        )
    )
    return {"command": row}


@router.delete("/channels/{twitch_id}/commands/{name}")
async def delete_command(
    twitch_id: int,
    name: str,
    body: DeleteBody,
    access: ChannelAccess = Depends(require_enabled_channel),
):
    actor = access.actor
    verify = _verifier(body.original)
    await run_db(_translate(lambda: twitch_commands.delete(twitch_id, actor, "dashboard", name, verify)))
    return {"ok": True}
