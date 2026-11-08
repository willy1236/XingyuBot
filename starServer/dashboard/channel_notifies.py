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

from .access import on_guild, require_guild_access
from .conflict import Conflict
from .db import run_db
from .errors import DashboardError
from .notify_fields import NotifySpec, parse_key
from .validity import channel_invalid_reason, role_invalid_reason

router = APIRouter(prefix="/dashboard")

#: Discord 訊息內容上限
MESSAGE_MAX_LENGTH = 2000

type Fields = dict[str, int | str | None]


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


def _field_names(spec: NotifySpec) -> list[str]:
    return ["channel_id", *(["role_id"] if spec.has_role else []), *(["message"] if spec.has_message else [])]


def _to_id(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    if not value.isascii() or not value.isdigit():
        raise DashboardError(400, "invalid_request")
    return int(value)


def _fields(spec: NotifySpec, raw: dict[str, str | None], *, strict: bool, blank_message_is_none: bool) -> Fields:
    """把 API 的字串欄位轉成資料庫的型別，只留該種類用得到的欄位。

    strict 為真時欄位必須齊全（original）；否則缺的選填欄位視為 null（values）。
    """
    names = _field_names(spec)
    if strict and any(name not in raw for name in names):
        raise DashboardError(400, "invalid_request")
    fields: Fields = {}
    channel_id = _to_id(raw.get("channel_id"))
    if channel_id is None:
        raise DashboardError(400, "invalid_request")
    fields["channel_id"] = channel_id
    if spec.has_role:
        fields["role_id"] = _to_id(raw.get("role_id"))
    if spec.has_message:
        message = raw.get("message")
        fields["message"] = None if blank_message_is_none and not message else message
    return fields


def _validate_message(fields: Fields) -> None:
    message = fields.get("message")
    if isinstance(message, str) and len(message) > MESSAGE_MAX_LENGTH:
        raise DashboardError(400, "invalid_field", field="message", reason=f"自訂文字不能超過 {MESSAGE_MAX_LENGTH} 字")


async def _validate(guild_id: int, spec: NotifySpec, fields: Fields) -> None:
    _validate_message(fields)

    def _check(guild):
        channel_reason = channel_invalid_reason(guild, fields["channel_id"], spec.scheduled)  # pyright: ignore[reportArgumentType]
        if channel_reason is not None:
            return "channel_id", channel_reason
        role_id = fields.get("role_id")
        if role_id is not None and (role_reason := role_invalid_reason(guild, role_id)) is not None:  # pyright: ignore[reportArgumentType]
            return "role_id", role_reason
        return None

    problem = await on_guild(guild_id, _check)
    if problem is not None:
        raise DashboardError(400, "invalid_field", field=problem[0], reason=problem[1])


def _current(guild_id: int, spec: NotifySpec) -> dict[str, str | None] | None:
    """該筆目前的值（欄位同 original，轉成字串）；不存在回 None。"""
    row = sqldb.get_notify_channel_fresh(guild_id, spec.channel_type)
    if row is None:
        return None
    return {name: None if (v := getattr(row, name)) is None else str(v) for name in _field_names(spec)}


def _conflict(guild_id: int, spec: NotifySpec) -> DashboardError:
    return Conflict(_current(guild_id, spec)).to_error()


@router.put("/guilds/{guild_id}/channel-notifies/{notify_type}")
async def put_channel_notify(notify_type: str, body: PutBody, guild_id: int = Depends(require_guild_access)):
    spec = _spec(notify_type)
    values = _fields(spec, body.values, strict=False, blank_message_is_none=True)
    original = None if body.original is None else _fields(spec, body.original, strict=True, blank_message_is_none=False)
    await _validate(guild_id, spec, values)

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
    original = _fields(spec, body.original, strict=True, blank_message_is_none=False)

    def _delete() -> None:
        if sqldb.delete_notify_channel_if(guild_id, spec.channel_type, original) == 0:
            raise _conflict(guild_id, spec)

    await run_db(_delete)
    return {"ok": True}
