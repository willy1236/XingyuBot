"""通知表單欄位的轉換與驗證，頻道通知與社群推播共用。"""

from .access import on_guild
from .errors import DashboardError
from .notify_fields import NotifySpec
from .validity import channel_invalid_reason, role_invalid_reason

#: Discord 訊息內容上限
MESSAGE_MAX_LENGTH = 2000

type Fields = dict[str, int | str | None]


def to_id(value: str | None) -> int | None:
    """API 的 Discord ID 字串 → int；空值回 None，不是數字拋 400 invalid_request。"""
    if value is None or value == "":
        return None
    if not value.isascii() or not value.isdigit():
        raise DashboardError(400, "invalid_request")
    return int(value)


def field_names(spec: NotifySpec) -> list[str]:
    """該種類用得到的欄位名稱，順序固定。"""
    return ["channel_id", *(["role_id"] if spec.has_role else []), *(["message"] if spec.has_message else [])]


def parse_fields(spec: NotifySpec, raw: dict[str, str | None], *, strict: bool, blank_message_is_none: bool) -> Fields:
    """把 API 的字串欄位轉成資料庫的型別，只留該種類用得到的欄位。

    strict 為真時欄位必須齊全（original）；否則缺的選填欄位視為 null（values）。
    """
    if strict and any(name not in raw for name in field_names(spec)):
        raise DashboardError(400, "invalid_request")
    channel_id = to_id(raw.get("channel_id"))
    if channel_id is None:
        raise DashboardError(400, "invalid_request")
    fields: Fields = {"channel_id": channel_id}
    if spec.has_role:
        fields["role_id"] = to_id(raw.get("role_id"))
    if spec.has_message:
        message = raw.get("message")
        fields["message"] = None if blank_message_is_none and not message else message
    return fields


async def validate_fields(guild_id: int, spec: NotifySpec, fields: Fields) -> None:
    """驗證自訂文字長度，以及頻道與身分組目前是否有效；失效回 400 invalid_field 附欄位與原因。"""
    message = fields.get("message")
    if isinstance(message, str) and len(message) > MESSAGE_MAX_LENGTH:
        raise DashboardError(400, "invalid_field", field="message", reason=f"自訂文字不能超過 {MESSAGE_MAX_LENGTH} 字")

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
