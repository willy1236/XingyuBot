"""實況主後台的聊天室過濾設定。"""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from starlib import twitch_moderation
from starlib.twitch_moderation import FilterValues, InvalidField
from starlib.twitch_speech_check import substitute

from . import twitch_control
from .channels import ChannelAccess, require_channel, require_enabled_channel
from .conflict import check_conflict
from .db import run_db
from .errors import DashboardError

router = APIRouter(prefix="/dashboard")


class Values(BaseModel):
    enabled: bool
    exempt_level: str
    params: dict[str, Any]
    notice: str | None
    silent: bool

    def fields(self) -> FilterValues:
        return {
            "enabled": self.enabled,
            "exempt_level": self.exempt_level,
            "params": self.params,
            "notice": self.notice,
            "silent": self.silent,
        }


class PutBody(BaseModel):
    values: Values
    original: Values


@router.get("/channels/{twitch_id}/moderation")
async def get_settings(twitch_id: int, _access: ChannelAccess = Depends(require_channel)):
    return await run_db(lambda: twitch_moderation.get_config(twitch_id))


@router.put("/channels/{twitch_id}/moderation/filters/{kind}")
async def update_filter(
    twitch_id: int,
    kind: str,
    body: PutBody,
    access: ChannelAccess = Depends(require_enabled_channel),
):
    if kind != "link":
        raise DashboardError(400, "invalid_field", field="kind", reason="目前只開放編輯連結過濾")
    values = body.values.fields()
    try:
        twitch_moderation.validate_link(values)
    except InvalidField as exc:
        raise DashboardError(400, "invalid_field", field=exc.field, reason=str(exc)) from None

    notice = values["notice"]
    if notice is not None and notice != body.original.notice:
        template = substitute(notice, {"filter": twitch_moderation.FILTER_LABELS[kind]})
        match await twitch_control.check_template(twitch_id, template):
            case "blocked":
                raise DashboardError(422, "automod_blocked")
            case "unavailable":
                raise DashboardError(503, "automod_unavailable")

    expected = twitch_moderation.comparable(body.original.fields())

    def verify(current: dict[str, str | None]) -> None:
        conflict = check_conflict(current, expected)
        if conflict is not None:
            raise conflict.to_error()

    actor = access.actor
    saved = await run_db(lambda: twitch_moderation.update_link(twitch_id, actor, values, verify))
    return {"filter": saved}
