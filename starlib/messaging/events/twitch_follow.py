from datetime import timedelta
from typing import ClassVar

from . import BusEvent


class TwitchFollowEvent(BusEvent):
    """Twitch 頻道被追隨。"""

    event_type: ClassVar[str] = "twitch.follow"
    ttl: ClassVar[timedelta] = timedelta(hours=1)
    receivers: ClassVar[tuple[str, ...]] = ("discord",)

    broadcaster_id: str  # 被追隨頻道的 Twitch ID
    broadcaster_name: str  # 被追隨頻道的顯示名稱
    follower_name: str  # 追隨者的顯示名稱
    follower_login: str  # 追隨者的 login
