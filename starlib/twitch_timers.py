"""Twitch 計時訊息的驗證與寫入。後台端點經這裡，規則只有一份。

每次寫入在同一個交易內：取頻道的鎖、讀目前的計時訊息、驗證、寫入、`twitch_audit.record_change`、commit，
最後通知 Twitch bot 重讀該頻道的計時訊息。欄位不合法或超過數量上限 raise `TimerInvalid`，不存在 raise `TimerMissing`，
後台的編輯衝突由呼叫端傳入的 `verify` 判斷。這些函式是同步的，要在 DB worker thread 上呼叫。
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlmodel import col, select

from starlib.database import TwitchTimer, sqldb
from starlib.messaging import cache_invalidation
from starlib.twitch_audit import AuditActor, record_change
from starlib.utils import nowtz

MESSAGE_MAX = 500
INTERVAL_MIN = 5
INTERVAL_MAX = 1440
MIN_LINES_MAX = 1000
#: 每個頻道最多幾則計時訊息
TIMERS_MAX = 20

#: 後台用：目前的值（`comparable` 的形狀），已被刪除時為 None；有衝突就 raise
type Verify = Callable[[dict[str, str | None] | None], None]


@dataclass(frozen=True, slots=True)
class TimerFields:
    """計時訊息可編輯的欄位。"""

    message: str
    interval_minutes: int
    min_chat_lines: int = 0
    enabled: bool = True


class TimerInvalid(Exception):
    """欄位不合法。field 是 message、interval_minutes、min_chat_lines，或超過數量上限時的 limit。"""

    def __init__(self, field: str, reason: str):
        super().__init__(f"{field}: {reason}")
        self.field = field
        self.reason = reason


class TimerMissing(Exception):
    """頻道沒有這則計時訊息。"""


def validate(fields: TimerFields) -> None:
    """格式與範圍檢查，不查資料庫。儲存前先用它擋掉明顯的錯誤，再花 AutoMod 檢查的額度。"""
    if not fields.message.strip():
        raise TimerInvalid("message", "訊息不能是空的")
    if len(fields.message) > MESSAGE_MAX:
        raise TimerInvalid("message", f"訊息不能超過 {MESSAGE_MAX} 字")
    if not INTERVAL_MIN <= fields.interval_minutes <= INTERVAL_MAX:
        raise TimerInvalid("interval_minutes", f"間隔要在 {INTERVAL_MIN} 到 {INTERVAL_MAX} 分鐘之間")
    if not 0 <= fields.min_chat_lines <= MIN_LINES_MAX:
        raise TimerInvalid("min_chat_lines", f"最少聊天量要在 0 到 {MIN_LINES_MAX} 則之間")


def snapshot(row: TwitchTimer) -> dict[str, Any]:
    """修改紀錄的欄位快照：可編輯的欄位，不含 id 與 updated_at。"""
    return {
        "message": row.message,
        "interval_minutes": row.interval_minutes,
        "min_chat_lines": row.min_chat_lines,
        "enabled": row.enabled,
    }


def comparable(values: dict[str, Any]) -> dict[str, str | None]:
    """比對編輯衝突用的字串形式（`conflict.check_conflict` 比的是字串）：布林是 true／false。"""
    return {
        "message": values["message"],
        "interval_minutes": str(values["interval_minutes"]),
        "min_chat_lines": str(values["min_chat_lines"]),
        "enabled": "true" if values["enabled"] else "false",
    }


def _rows(twitch_id: int, *, lock: bool = False) -> list[TwitchTimer]:
    """頻道目前的計時訊息，一律重讀資料庫；lock 為真時鎖住這些列。"""
    stmt = (
        select(TwitchTimer)
        .where(TwitchTimer.twitch_id == twitch_id)
        .order_by(col(TwitchTimer.id))
        .execution_options(populate_existing=True)
    )
    if lock:
        stmt = stmt.with_for_update()
    return list(sqldb.session.exec(stmt).all())


def list_timers(twitch_id: int) -> list[TwitchTimer]:
    """頻道的全部計時訊息，依 id 排序。"""
    return _rows(twitch_id)


def _begin(twitch_id: int) -> list[TwitchTimer]:
    """取頻道的計時訊息寫入鎖（交易層級，同頻道並行新增也不會超過上限），回傳鎖住的列；commit 或 rollback 時釋放。"""
    sqldb.session.connection().execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": f"twitch_timer:{twitch_id}"}
    )
    return _rows(twitch_id, lock=True)


def _finish(twitch_id: int) -> None:
    sqldb.commit()
    cache_invalidation.invalidate("twitch_timer", str(twitch_id))


def _transaction[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    """任何例外都 rollback，不讓取到的鎖留在交易裡。"""

    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return func(*args, **kwargs)
        except BaseException:
            sqldb.session.rollback()
            raise

    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper


def _locate(rows: list[TwitchTimer], timer_id: int, verify: Verify | None) -> TwitchTimer:
    """依 id 找計時訊息；找不到時，有 verify 就讓它判斷（通常 raise 已被刪除的衝突），否則 raise TimerMissing。"""
    row = next((r for r in rows if r.id == timer_id), None)
    if row is None:
        if verify is not None:
            verify(None)
        raise TimerMissing(str(timer_id))
    if verify is not None:
        verify(comparable(snapshot(row)))
    return row


@_transaction
def create(twitch_id: int, actor: AuditActor, fields: TimerFields) -> TwitchTimer:
    """新增計時訊息；頻道已有 `TIMERS_MAX` 則時 raise TimerInvalid("limit")。"""
    validate(fields)
    rows = _begin(twitch_id)
    if len(rows) >= TIMERS_MAX:
        raise TimerInvalid("limit", f"每個頻道最多 {TIMERS_MAX} 則計時訊息")
    row = TwitchTimer(
        twitch_id=twitch_id,
        message=fields.message,
        interval_minutes=fields.interval_minutes,
        min_chat_lines=fields.min_chat_lines,
        enabled=fields.enabled,
        updated_at=nowtz(),
    )
    sqldb.session.add(row)
    sqldb.session.flush()
    record_change(twitch_id, actor, "dashboard", "timer", str(row.id), "create", None, snapshot(row))
    _finish(twitch_id)
    return row


@_transaction
def update(
    twitch_id: int, actor: AuditActor, timer_id: int, fields: TimerFields, verify: Verify | None = None
) -> TwitchTimer:
    """編輯計時訊息。"""
    validate(fields)
    row = _locate(_begin(twitch_id), timer_id, verify)
    before = snapshot(row)
    row.message = fields.message
    row.interval_minutes = fields.interval_minutes
    row.min_chat_lines = fields.min_chat_lines
    row.enabled = fields.enabled
    row.updated_at = nowtz()
    sqldb.session.flush()
    record_change(twitch_id, actor, "dashboard", "timer", str(timer_id), "update", before, snapshot(row))
    _finish(twitch_id)
    return row


@_transaction
def delete(twitch_id: int, actor: AuditActor, timer_id: int, verify: Verify | None = None) -> None:
    """刪除計時訊息。"""
    row = _locate(_begin(twitch_id), timer_id, verify)
    before = snapshot(row)
    sqldb.session.delete(row)
    sqldb.session.flush()
    record_change(twitch_id, actor, "dashboard", "timer", str(timer_id), "delete", before, None)
    _finish(twitch_id)
