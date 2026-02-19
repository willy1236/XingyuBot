from datetime import datetime
from typing import ClassVar

import discord
from pydantic import BaseModel, Field


class BaseEvent(BaseModel):
    """
    所有事件的基底類別
    透過繼承此類別來創建新的事件類別，用以取代以Enum或字串作為事件類型的方式，提供更強的類型安全和可讀性。
    事件類別可以包含任意屬性，並且可以在 Eventbus 中攜帶相關數據。
    """

    timestamp: datetime = Field(default_factory=datetime.now)
    source: str = "system"

    # Pydantic 設定，允許任意類型
    class Config:
        arbitrary_types_allowed = True


class TwitchStreamEvent(BaseEvent):
    """
    Twitch 直播事件，包含直播開始、結束、訂閱等相關事件。
    """

    content: str | None = None
    to_discord_channel: int = 566533708371329026
    embed: discord.Embed | None = None
