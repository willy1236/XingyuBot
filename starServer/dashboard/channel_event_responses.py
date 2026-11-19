"""實況主後台：事件回應（開台、追隨、訂閱、續訂、贈訂、Raid）。

GET    /dashboard/channels/{twitch_id}/event-responses         六種事件的開關、文字、是否為預設與可用變數
PUT    /dashboard/channels/{twitch_id}/event-responses/{kind}  設定，body `{values, original}`
DELETE /dashboard/channels/{twitch_id}/event-responses/{kind}  恢復預設，body `{original}`

`original` 是打開表單時看到的有效設定（含預設值），和資料庫目前的有效設定不同時回 409 conflict
（形狀同伺服器後台，欄位值是字串，見 `twitch_event_responses.comparable`）。
修改要求頻道已啟用（409 channel_not_enabled）；文字不合法回 400 invalid_field，不認得的事件種類回 404 event_kind_not_found。
儲存的文字有變時先過頻道 AutoMod：擋下回 422 automod_blocked，無法檢查回 503 automod_unavailable，兩者都不儲存。
"""

from collections.abc import Callable

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from starlib import twitch_event_responses
from starlib.twitch_event_responses import EventResponse, EventResponseInvalid, UnknownEventKind, Verify

from . import twitch_control
from .channels import require_channel, require_enabled_channel
from .conflict import check_conflict
from .db import run_db
from .errors import DashboardError
from .session import SessionInfo, TwitchIdentity, audit_actor, require_any_session

router = APIRouter(prefix="/dashboard")


class Values(BaseModel):
    enabled: bool
    template: str


class PutBody(BaseModel):
    values: Values
    original: Values


class DeleteBody(BaseModel):
    original: Values


def _json(response: EventResponse) -> dict:
    return {
        "kind": response.kind,
        "enabled": response.enabled,
        "template": response.template,
        "is_default": response.is_default,
        "variables": response.variables,
    }


def _verifier(original: Values) -> Verify:
    """資料庫目前的有效設定和打開表單時不同就 raise 409 conflict。"""
    expected = twitch_event_responses.comparable(original.model_dump())

    def verify(current: dict[str, str | None]) -> None:
        conflict = check_conflict(current, expected)
        if conflict is not None:
            raise conflict.to_error()

    return verify


def _translate[T](work: Callable[[], T]) -> Callable[[], T]:
    """在 DB worker thread 上執行時，把共用模組的驗證錯誤轉成後台的錯誤回應。"""

    def run() -> T:
        try:
            return work()
        except EventResponseInvalid as e:
            raise DashboardError(400, "invalid_field", field=e.field, reason=e.reason) from None
        except UnknownEventKind:
            raise DashboardError(404, "event_kind_not_found") from None

    return run


async def _check_automod(twitch_id: int, template: str) -> None:
    match await twitch_control.check_template(twitch_id, template):
        case "blocked":
            raise DashboardError(422, "automod_blocked")
        case "unavailable":
            raise DashboardError(503, "automod_unavailable")


@router.get("/channels/{twitch_id}/event-responses")
async def list_event_responses(twitch_id: int, _channel: TwitchIdentity = Depends(require_channel)):
    rows = await run_db(lambda: [_json(r) for r in twitch_event_responses.list_responses(twitch_id)])
    return {"event_responses": rows}


@router.put("/channels/{twitch_id}/event-responses/{kind}")
async def save_event_response(
    twitch_id: int,
    kind: str,
    body: PutBody,
    info: SessionInfo = Depends(require_any_session),
    _channel: TwitchIdentity = Depends(require_enabled_channel),
):
    template = body.values.template
    await run_db(_translate(lambda: twitch_event_responses.validate(kind, template)))
    # 文字沒變（只切換開關）或就是預設文字時不花 AutoMod 檢查的額度，AutoMod 暫時無法檢查時也能開關
    if template != body.original.template and template != twitch_event_responses.DEFAULTS[kind]:
        await _check_automod(twitch_id, template)
    actor = audit_actor(info)
    verify = _verifier(body.original)
    response = await run_db(
        _translate(
            lambda: _json(
                twitch_event_responses.save(twitch_id, actor, "dashboard", kind, body.values.enabled, template, verify)
            )
        )
    )
    return {"event_response": response}


@router.delete("/channels/{twitch_id}/event-responses/{kind}")
async def reset_event_response(
    twitch_id: int,
    kind: str,
    body: DeleteBody,
    info: SessionInfo = Depends(require_any_session),
    _channel: TwitchIdentity = Depends(require_enabled_channel),
):
    actor = audit_actor(info)
    verify = _verifier(body.original)
    response = await run_db(
        _translate(lambda: _json(twitch_event_responses.reset(twitch_id, actor, "dashboard", kind, verify)))
    )
    return {"event_response": response}
