"""用 Twitch ID 查是不是域民；只以 auth server 為準，不寫入也不保存任何資料。"""

from dataclasses import dataclass
from uuid import UUID

from .client import DirectoryUnavailable
from .resolver import _get_directory


@dataclass(frozen=True)
class TwitchMember:
    account_id: UUID
    username: str | None  # 域民代號


class NotMember:
    """查無此人或域民停權中"""


class MemberUnknown:
    """auth server 沒給出明確答案，不能當成不是域民"""


TwitchLookup = TwitchMember | NotMember | MemberUnknown


async def lookup_twitch_member(twitch_id: str | int) -> TwitchLookup:
    """不 raise；auth server 連不上、逾時、5xx、401、非 auth server 自己的 404 都回 MemberUnknown"""
    from starlib.settings import get_settings

    try:
        account = await _get_directory().find_by_passport(get_settings().AUTH_TWITCH_PROVIDER, str(twitch_id))
    except DirectoryUnavailable:
        return MemberUnknown()
    if account is None or account.suspended:
        return NotMember()
    return TwitchMember(account_id=account.account_id, username=account.username)

