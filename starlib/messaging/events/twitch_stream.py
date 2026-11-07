from datetime import timedelta
from typing import ClassVar

from pydantic import AwareDatetime

from . import BusEvent


class TwitchStreamOnlineEvent(BusEvent):
    """Twitch 頻道開台。欄位是 Twitch Helix streams 回傳的直播資訊，加上實況主頭像。"""

    event_type: ClassVar[str] = "twitch.stream_online"
    ttl: ClassVar[timedelta] = timedelta(minutes=10)
    receivers: ClassVar[tuple[str, ...]] = ("discord",)

    broadcaster_id: str  # 開台頻道的 Twitch ID
    broadcaster_name: str  # 開台頻道的顯示名稱
    profile_image_url: str | None = None  # 實況主頭像網址，查不到時為 None

    # 直播資訊（Helix streams）
    stream_id: str
    user_login: str
    game_id: str
    game_name: str
    stream_type: str
    title: str
    viewer_count: int
    started_at: AwareDatetime  # 開始直播的時間（含時區），也是開台通知搶佔的比較值
    language: str
    thumbnail_url: str
    tag_ids: list[str | None] = []
    tags: list[str | None] = []
    is_mature: bool = False


class TwitchStreamOfflineEvent(BusEvent):
    """Twitch 頻道下播。"""

    event_type: ClassVar[str] = "twitch.stream_offline"
    ttl: ClassVar[timedelta] = timedelta(minutes=5)
    receivers: ClassVar[tuple[str, ...]] = ("discord",)

    broadcaster_id: str  # 下播頻道的 Twitch ID
    broadcaster_name: str  # 下播頻道的顯示名稱
