"""跨 process 訊息：事件廣播（本套件）、請求／回應與快取失效（各自的模組）共用同一條 Redis 連線。

正式程式一律用 get_bus()；直接建立 MessageBus 只給測試用。線路格式見 docs/messaging-contract.md。
"""

from .bus import Delivery, Handler, MessageBus, get_bus
from .connection import BusUnavailable
from .events import BusEvent

__all__ = ["BusEvent", "BusUnavailable", "Delivery", "Handler", "MessageBus", "get_bus"]
