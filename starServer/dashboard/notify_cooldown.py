"""測試通知的冷卻：記憶體內，key 是 guild × 種類鍵 × 帳號，所有管理員共用。

只在 web 的事件迴圈上呼叫，acquire 到 commit／release 之間不會被別的請求插入檢查。
發送前先佔位，同時按下的第二個請求會看到佔位；成功後改記成功時間，失敗就移除佔位，不計入冷卻。
"""

import time

from .errors import DashboardError

COOLDOWN_SECONDS = 60
#: 佔位期間（正在發送）其他請求建議的重試秒數
PENDING_RETRY_SECONDS = 3

#: None 是「發送中」佔位，否則是成功發送的 monotonic 時間
_state: dict[str, float | None] = {}


def cooldown_key(guild_id: int, notify_key: str, account_id: str | None) -> str:
    return f"{guild_id}:{notify_key}:{account_id or ''}"


def remaining(key: str) -> int:
    """剩餘冷卻秒數（無條件進位）；沒有冷卻回 0。"""
    if key not in _state:
        return 0
    sent_at = _state[key]
    if sent_at is None:
        return PENDING_RETRY_SECONDS
    left = sent_at + COOLDOWN_SECONDS - time.monotonic()
    if left <= 0:
        del _state[key]
        return 0
    return int(left) + 1


def acquire(key: str) -> None:
    """佔位；冷卻中或正在發送時拋 429 cooldown 附 retry_after。"""
    if (left := remaining(key)) > 0:
        raise DashboardError(429, "cooldown", retry_after=left)
    _state[key] = None


def commit(key: str) -> None:
    _state[key] = time.monotonic()


def release(key: str) -> None:
    _state.pop(key, None)
