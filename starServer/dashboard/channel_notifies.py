"""頻道通知的新增、修改、刪除：
PUT    /dashboard/guilds/{id}/channel-notifies/{notify_type}  body `{values, original}`，original 為 null 是新增
DELETE /dashboard/guilds/{id}/channel-notifies/{notify_type}  body `{original}`

修改與刪除用條件式寫入（WHERE 帶原始值），後到的一定被擋下並回 409 conflict；新增遇到已存在回 409 already_exists。
`values`、`original` 只含該種類用得到的欄位，沒打勾的欄位不比對也不動，指令設的值才不會讓比對永遠失敗。
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from starlib import sqldb
from starlib.exceptions import DataExistError

from .access import require_guild_access
from .conflict import Conflict
from .db import run_db
from .errors import DashboardError
from .notify_fields import NotifySpec, parse_key
from .notify_input import field_names, parse_fields, validate_fields

router = APIRouter(prefix="/dashboard")


class PutBody(BaseModel):
    #: 表單欄位值；Discord ID 用字串
    values: dict[str, str | None]
    #: 打開表單時看到的值；null 表示新增
    original: dict[str, str | None] | None = None


class DeleteBody(BaseModel):
    original: dict[str, str | None]


def _spec(notify_type: str) -> NotifySpec:
    try:
        spec = parse_key(notify_type)
    except KeyError:
        raise DashboardError(400, "invalid_request") from None
    if spec.kind != "channel":
        raise DashboardError(400, "invalid_request")
    return spec


def _current(guild_id: int, spec: NotifySpec) -> dict[str, str | None] | None:
    """該筆目前的值（欄位同 original，轉成字串）；不存在回 None。"""
    row = sqldb.get_notify_channel_fresh(guild_id, spec.channel_type)
    if row is None:
        return None
    return {name: None if (v := getattr(row, name)) is None else str(v) for name in field_names(spec)}


def _conflict(guild_id: int, spec: NotifySpec) -> DashboardError:
    return Conflict(_current(guild_id, spec)).to_error()


@router.put("/guilds/{guild_id}/channel-notifies/{notify_type}")
async def put_channel_notify(notify_type: str, body: PutBody, guild_id: int = Depends(require_guild_access)):
    spec = _spec(notify_type)
    values = parse_fields(spec, body.values, strict=False, blank_message_is_none=True)
    original = None if body.original is None else parse_fields(spec, body.original, strict=True, blank_message_is_none=False)
    await validate_fields(guild_id, spec, values)

    def _write() -> None:
        if original is None:
            try:
                sqldb.insert_notify_channel(
                    guild_id, spec.channel_type, values["channel_id"], values.get("role_id"), values.get("message")  # pyright: ignore[reportArgumentType]
                )
            except DataExistError:
                raise DashboardError(409, "already_exists", current=_current(guild_id, spec)) from None
        elif sqldb.update_notify_channel_if(guild_id, spec.channel_type, original, values) == 0:
            raise _conflict(guild_id, spec)

    await run_db(_write)
    return {"values": {k: None if v is None else str(v) for k, v in values.items()}}


@router.delete("/guilds/{guild_id}/channel-notifies/{notify_type}")
async def delete_channel_notify(notify_type: str, body: DeleteBody, guild_id: int = Depends(require_guild_access)):
    spec = _spec(notify_type)
    original = parse_fields(spec, body.original, strict=True, blank_message_is_none=False)

    def _delete() -> None:
        if sqldb.delete_notify_channel_if(guild_id, spec.channel_type, original) == 0:
            raise _conflict(guild_id, spec)

    await run_db(_delete)
    return {"ok": True}
