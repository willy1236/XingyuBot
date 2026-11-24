"""實況主後台的聊天室過濾設定。"""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, StrictInt

from starlib import twitch_moderation
from starlib.twitch_moderation import FilterValues, InvalidField, SettingsValues, Stage
from starlib.twitch_speech_check import substitute

from . import twitch_control
from .channels import ChannelAccess, require_channel, require_enabled_channel
from .conflict import check_conflict
from .db import run_db
from .errors import DashboardError

router = APIRouter(prefix="/dashboard")


class StageInput(BaseModel):
    action: str
    duration: StrictInt | None = None

    def fields(self) -> Stage:
        return {"action": self.action, "duration": self.duration}


class FilterInput(BaseModel):
    enabled: bool
    exempt_level: str
    params: dict[str, Any]
    notice: str | None
    silent: bool
    stages: list[StageInput] | None = None

    def fields(self) -> FilterValues:
        values: FilterValues = {
            "enabled": self.enabled,
            "exempt_level": self.exempt_level,
            "params": self.params,
            "notice": self.notice,
            "silent": self.silent,
        }
        if "stages" in self.model_fields_set:
            values["stages"] = [stage.fields() for stage in self.stages] if self.stages is not None else None
        return values


class FilterPutBody(BaseModel):
    values: FilterInput
    original: FilterInput


class SettingsInput(BaseModel):
    stages: list[StageInput]
    strike_reset_minutes: StrictInt
    permit_seconds: StrictInt

    def fields(self) -> SettingsValues:
        return {
            "stages": [stage.fields() for stage in self.stages],
            "strike_reset_minutes": self.strike_reset_minutes,
            "permit_seconds": self.permit_seconds,
        }


class SettingsPutBody(BaseModel):
    values: SettingsInput
    original: SettingsInput


def _verify_original(expected: dict[str, str | None]) -> twitch_moderation.Verify:
    def verify(current: dict[str, str | None]) -> None:
        conflict = check_conflict(current, expected)
        if conflict is not None:
            raise conflict.to_error()

    return verify


@router.get("/channels/{twitch_id}/moderation")
async def get_settings(twitch_id: int, _access: ChannelAccess = Depends(require_channel)):
    return await run_db(lambda: twitch_moderation.get_config(twitch_id))


@router.put("/channels/{twitch_id}/moderation/filters/{kind}")
async def update_filter(
    twitch_id: int,
    kind: str,
    body: FilterPutBody,
    access: ChannelAccess = Depends(require_enabled_channel),
):
    values = body.values.fields()
    try:
        twitch_moderation.validate_filter(kind, values)
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

    verify = _verify_original(twitch_moderation.comparable(body.original.fields()))
    actor = access.actor
    saved = await run_db(lambda: twitch_moderation.update_filter(twitch_id, kind, actor, values, verify))
    return {"filter": saved}


@router.put("/channels/{twitch_id}/moderation/settings")
async def update_settings(
    twitch_id: int,
    body: SettingsPutBody,
    access: ChannelAccess = Depends(require_enabled_channel),
):
    values = body.values.fields()
    verify = _verify_original(twitch_moderation.comparable_settings(body.original.fields()))
    try:
        saved = await run_db(lambda: twitch_moderation.update_settings(twitch_id, access.actor, values, verify))
    except InvalidField as exc:
        raise DashboardError(400, "invalid_field", field=exc.field, reason=str(exc)) from None
    return {"settings": saved}
