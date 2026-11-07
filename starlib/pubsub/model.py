from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BaseEvent(BaseModel):
    """
    所有事件的基底類別
    透過繼承此類別來創建新的事件類別，用以取代以Enum或字串作為事件類型的方式，提供更強的類型安全和可讀性。
    事件類別可以包含任意屬性，並且可以在 Eventbus 中攜帶相關數據。
    """

    timestamp: datetime = Field(default_factory=datetime.now)
    source: str = "system"

    model_config = ConfigDict(arbitrary_types_allowed=True)
