"""
### 模組：pubsub
發布-訂閱系統，提供事件驅動的架構，讓不同模組之間可以通過事件進行通信和協作。
"""

from .client import StarEventBus

__all__ = [
    "StarEventBus",
]
