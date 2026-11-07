from datetime import timedelta
from typing import ClassVar

from . import BusEvent


class TwitchRaidEvent(BusEvent):
    """其他實況主帶觀眾突襲 Twitch 頻道。"""

    event_type: ClassVar[str] = "twitch.raid"
    ttl: ClassVar[timedelta] = timedelta(minutes=10)
    receivers: ClassVar[tuple[str, ...]] = ("discord",)

    to_broadcaster_id: str  # 被突襲頻道的 Twitch ID
    to_broadcaster_name: str  # 被突襲頻道的顯示名稱
    from_broadcaster_name: str  # 發起突襲的實況主顯示名稱
    viewers: int  # 突襲帶來的觀眾數


class TwitchSubscribeEvent(BusEvent):
    """新訂閱（不含贈送）。"""

    event_type: ClassVar[str] = "twitch.subscribe"
    ttl: ClassVar[timedelta] = timedelta(hours=1)
    receivers: ClassVar[tuple[str, ...]] = ("discord",)

    broadcaster_id: str  # 被訂閱頻道的 Twitch ID
    user_name: str  # 訂閱者的顯示名稱


class TwitchSubscriptionMessageEvent(BusEvent):
    """續訂訊息。"""

    event_type: ClassVar[str] = "twitch.subscription_message"
    ttl: ClassVar[timedelta] = timedelta(hours=1)
    receivers: ClassVar[tuple[str, ...]] = ("discord",)

    broadcaster_id: str  # 被訂閱頻道的 Twitch ID
    broadcaster_name: str  # 被訂閱頻道的顯示名稱
    user_name: str  # 訂閱者的顯示名稱
    tier: str  # Twitch 原始層級值："1000"、"2000"、"3000"
    duration_months: int  # 這次訂閱的月數
    cumulative_months: int | None = None  # 累積訂閱月數；訂閱者不分享時為 None
    message: str | None = None  # 訂閱者附的訊息；沒有時為 None


class TwitchRedemptionEvent(BusEvent):
    """頻道點數兌換。"""

    event_type: ClassVar[str] = "twitch.redemption"
    ttl: ClassVar[timedelta] = timedelta(hours=1)
    receivers: ClassVar[tuple[str, ...]] = ("discord",)

    broadcaster_id: str  # 頻道的 Twitch ID
    user_name: str  # 兌換者的顯示名稱
    user_login: str  # 兌換者的 login
    reward_title: str  # 兌換項目名稱
    user_input: str | None = None  # 兌換者輸入的文字；沒有時為 None


class TwitchPredictionResultEvent(BusEvent):
    """預測結束且有獲勝選項。"""

    event_type: ClassVar[str] = "twitch.prediction_result"
    ttl: ClassVar[timedelta] = timedelta(hours=1)
    receivers: ClassVar[tuple[str, ...]] = ("discord",)

    broadcaster_name: str  # 頻道的顯示名稱
    title: str  # 預測標題
    outcome_title: str  # 獲勝選項名稱
    users: int  # 成功預測的人數


class TwitchWhisperEvent(BusEvent):
    """Twitch bot 收到的私訊。"""

    event_type: ClassVar[str] = "twitch.whisper"
    ttl: ClassVar[timedelta] = timedelta(hours=1)
    receivers: ClassVar[tuple[str, ...]] = ("discord",)

    user_name: str  # 傳私訊者的顯示名稱
    message: str  # 私訊內容
