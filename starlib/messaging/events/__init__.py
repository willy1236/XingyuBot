"""跨 process 事件的 model 與登錄表。

具體事件放在本目錄的各模組，並在本檔最下方匯入，讓登錄表在 bus 啟動前就完整：
bus 依登錄表替每個接收服務建立 consumer group、修剪過期事件。
"""

from datetime import datetime, timedelta
from typing import Any, ClassVar

from pydantic import AwareDatetime, BaseModel, ConfigDict

# event_type -> model，由 BusEvent.__init_subclass__ 自動登錄
registry: dict[str, type[BusEvent]] = {}


class BusEvent(BaseModel):
    """跨 process 事件的基底。子類別定義 event_type、ttl、receivers 三個 ClassVar 就會自動登錄。"""

    model_config = ConfigDict(extra="ignore", frozen=True)

    event_type: ClassVar[str]  # 跨語言的事件名稱，例如 "twitch.follow"
    ttl: ClassVar[timedelta]  # 補送時效，從 occurred_at 起算
    receivers: ClassVar[tuple[str, ...]]  # 接收服務名稱，例如 ("discord",)

    occurred_at: AwareDatetime  # 事件發生時間（含時區）

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if "event_type" not in cls.__dict__:
            return
        if not hasattr(cls, "ttl") or not hasattr(cls, "receivers"):
            raise TypeError(f"{cls.__qualname__} 定義了 event_type，也要定義 ttl 與 receivers")
        existing = registry.get(cls.event_type)
        # 同一個 class 重新匯入（模組重新載入）時取代；不同 class 撞名代表契約衝突
        if existing is not None and (existing.__module__, existing.__qualname__) != (cls.__module__, cls.__qualname__):
            raise TypeError(f"event_type {cls.event_type!r} 已被 {existing.__module__}.{existing.__qualname__} 使用")
        registry[cls.event_type] = cls

    def expired(self, now: datetime) -> bool:
        return now - self.occurred_at > self.ttl


__all__ = ["BusEvent", "registry"]

# 具體事件：匯入後才會登錄（要放在 BusEvent 定義之後）
from . import twitch_activity, twitch_follow, twitch_stream  # noqa: E402,F401
