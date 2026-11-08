"""通知種類的欄位對照：後台所有卡共用的種類鍵、顯示名稱與可用欄位。

NotifyChannelType（1～13）和 NotifyCommunityType（1～5）的整數值會重疊，所以後台一律用字串種類鍵
`channel:<值>`、`community:<值>`。有效的種類只有下面表列的那些；已廢棄的 DynamicVoice（9）與資料庫裡
不在表內的種類，parse_key 會拒絕，一覽也會略過。
"""

from dataclasses import dataclass
from typing import Literal

from starlib.database import NotifyChannelType, NotifyCommunityType, PlatformType
from starlib.fileDatabase import Jsondb


@dataclass(frozen=True)
class NotifySpec:
    key: str
    kind: Literal["channel", "community"]
    type_value: int
    name: str
    #: 身分組、自訂文字是否為該種類用得到的欄位。資料庫可能存著沒打勾的值，後台不顯示也不改
    has_role: bool
    has_message: bool
    #: 定時通知：持續編輯同一則訊息，頻道需要 Read Message History
    scheduled: bool = False
    #: 社群推播的平台，頻道通知為 None
    platform: PlatformType | None = None

    @property
    def channel_type(self) -> NotifyChannelType:
        assert self.kind == "channel"
        return NotifyChannelType(self.type_value)

    @property
    def community_type(self) -> NotifyCommunityType:
        assert self.kind == "community"
        return NotifyCommunityType(self.type_value)


def _channel_name(t: NotifyChannelType) -> str:
    return Jsondb.options.channel_set_option[str(t.value)].zh_tw or str(t.name)


def _twitch_name(t: NotifyCommunityType) -> str:
    return "Twitch " + (Jsondb.options.twitch_notify_option[str(t.value)].zh_tw or str(t.name))


def _channel(t: NotifyChannelType, *, role: bool = False, message: bool = False, scheduled: bool = False) -> NotifySpec:
    return NotifySpec(f"channel:{t.value}", "channel", t.value, _channel_name(t), role, message, scheduled)


def _community(t: NotifyCommunityType, name: str, platform: PlatformType, *, message: bool) -> NotifySpec:
    return NotifySpec(f"community:{t.value}", "community", t.value, name, True, message, False, platform)


_C = NotifyChannelType
_M = NotifyCommunityType

CHANNEL_SPECS: tuple[NotifySpec, ...] = (
    _channel(_C.AllAnnouncements, role=True),
    _channel(_C.BotUpdates, role=True),
    _channel(_C.MajorQuakeNotifications, role=True),
    _channel(_C.SlightQuakeNotifications, role=True),
    _channel(_C.WeatherWarning, role=True),
    _channel(_C.WeatherForecast, scheduled=True),
    _channel(_C.ApexRotation, scheduled=True),
    _channel(_C.MemberJoin, message=True),
    _channel(_C.MemberLeave, message=True),
    _channel(_C.JoinLog),
    _channel(_C.LeaveLog),
    _channel(_C.VoiceLog),
)

COMMUNITY_SPECS: tuple[NotifySpec, ...] = (
    _community(_M.TwitchLive, _twitch_name(_M.TwitchLive), PlatformType.Twitch, message=True),
    _community(_M.TwitchVideo, _twitch_name(_M.TwitchVideo), PlatformType.Twitch, message=True),
    _community(_M.TwitchClip, _twitch_name(_M.TwitchClip), PlatformType.Twitch, message=True),
    _community(_M.Youtube, "YouTube", PlatformType.Google, message=True),
    _community(_M.TwitterTweet, "Twitter", PlatformType.Twitter, message=False),
)

_BY_KEY: dict[str, NotifySpec] = {s.key: s for s in (*CHANNEL_SPECS, *COMMUNITY_SPECS)}


def parse_key(key: str) -> NotifySpec:
    """字串種類鍵 → 規格。不是有效的種類鍵時拋 KeyError。"""
    return _BY_KEY[key]


def channel_spec(notify_type: NotifyChannelType | int) -> NotifySpec | None:
    """資料庫的頻道通知種類 → 規格；不在對照表（例如已廢棄的種類）回 None。"""
    return _BY_KEY.get(f"channel:{int(notify_type)}")


def community_spec(notify_type: NotifyCommunityType | int) -> NotifySpec | None:
    return _BY_KEY.get(f"community:{int(notify_type)}")
