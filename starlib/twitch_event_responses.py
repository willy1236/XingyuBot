"""Twitch 事件回應（開台、追隨、訂閱、續訂、贈訂、Raid）的預設文字、驗證與寫入。

後台端點與 bot 的事件 handler 都經這裡：預設文字與可用變數只有一份，沒有資料列的事件視為開啟並使用預設文字。
每次寫入在同一個交易內：取頻道的鎖、讀目前的設定、比對編輯衝突、驗證、寫入、`twitch_audit.record_change`、commit，
最後通知 Twitch bot 重讀該頻道的事件回應。驗證不過 raise `EventResponseInvalid`，不認得的事件種類 raise `UnknownEventKind`，
後台的編輯衝突由呼叫端傳入的 `verify` 判斷。這些函式是同步的，要在 DB worker thread 上呼叫。
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlmodel import select

from starlib.database import TwitchEventResponse, sqldb
from starlib.messaging import cache_invalidation
from starlib.twitch_audit import AuditActor, AuditSource, record_change
from starlib.utils import nowtz

TEMPLATE_MAX = 500

#: 事件種類，順序就是後台列出的順序
KINDS = ("stream_online", "follow", "subscribe", "resubscribe", "gift", "raid")

#: 沒有資料列時使用的文字；放在程式裡，之後調整預設不必改資料庫
DEFAULTS: dict[str, str] = {
    "stream_online": "{channel} 正在直播 {game}！{title}",
    "follow": "感謝 {user} 的追隨！",
    "subscribe": "感謝 {user} 的訂閱！",
    "resubscribe": "感謝 {user} 的訂閱！累積訂閱 {months} 個月！",
    "gift": "感謝 {user} 送出 {amount} 份訂閱！",
    "raid": "{user} 帶了 {viewers} 位觀眾降落在 {channel} 的頻道！",
}

_VARIABLE_HELP = {
    "user": "觸發事件的人",
    "channel": "頻道名稱",
    "months": "累積訂閱月數",
    "amount": "送出的訂閱份數",
    "viewers": "帶來的觀眾人數",
    "uptime": "已開台時間",
    "game": "目前分類",
    "title": "目前標題",
}

#: 各事件的可用變數；其餘變數在模板裡照樣能用，但後台只列這些
_VARIABLES: dict[str, tuple[str, ...]] = {
    "stream_online": ("channel", "game", "title", "uptime"),
    "follow": ("user", "channel"),
    "subscribe": ("user", "channel"),
    "resubscribe": ("user", "months", "channel"),
    "gift": ("user", "amount", "channel"),
    "raid": ("user", "viewers", "channel"),
}

#: 比對編輯衝突用的欄位形狀；已被刪除（恢復預設）的設定就是預設值，所以永遠有目前的值
type Verify = Callable[[dict[str, str | None]], None]


@dataclass(frozen=True, slots=True)
class EventResponse:
    kind: str
    enabled: bool
    template: str
    #: 沒有資料列，正在使用預設文字並開啟
    is_default: bool

    @property
    def variables(self) -> list[dict[str, str]]:
        return [{"token": "{" + name + "}", "description": _VARIABLE_HELP[name]} for name in _VARIABLES[self.kind]]


class EventResponseInvalid(Exception):
    """欄位不合法。field 是 template 或 enabled。"""

    def __init__(self, field: str, reason: str):
        super().__init__(f"{field}: {reason}")
        self.field = field
        self.reason = reason


class UnknownEventKind(Exception):
    """不認得的事件種類。"""


def default_response(kind: str) -> EventResponse:
    return EventResponse(kind, True, DEFAULTS[kind], True)


def _effective(kind: str, row: TwitchEventResponse | None) -> EventResponse:
    if row is None:
        return default_response(kind)
    return EventResponse(kind, row.enabled, row.template, False)


def comparable(values: dict[str, Any]) -> dict[str, str | None]:
    """比對編輯衝突用的字串形式（`conflict.check_conflict` 比的是字串）；values 含 enabled 與 template。"""
    return {"enabled": "true" if values["enabled"] else "false", "template": values["template"]}


def _snapshot(enabled: bool, template: str) -> dict[str, Any]:
    return {"enabled": enabled, "template": template}


def _check_kind(kind: str) -> None:
    if kind not in DEFAULTS:
        raise UnknownEventKind(kind)


def validate(kind: str, template: str) -> None:
    """儲存前的檢查（事件種類、文字長度），不寫入。先用它擋掉明顯的錯誤，再花 AutoMod 檢查的額度。"""
    _check_kind(kind)
    if not template.strip():
        raise EventResponseInvalid("template", "回應不能是空的")
    if len(template) > TEMPLATE_MAX:
        raise EventResponseInvalid("template", f"回應不能超過 {TEMPLATE_MAX} 字")


def list_responses(twitch_id: int) -> list[EventResponse]:
    """頻道的六種事件回應，沒有自訂過的種類是預設值。"""
    rows = {row.event_kind: row for row in sqldb.list_twitch_event_responses(twitch_id)}
    return [_effective(kind, rows.get(kind)) for kind in KINDS]


def _begin(twitch_id: int, kind: str) -> TwitchEventResponse | None:
    """取頻道的事件回應寫入鎖（交易層級的 advisory lock），再鎖住這一種的資料列；隨 commit 或 rollback 釋放。

    之後到 commit 之前只用 `sqldb.session`，不呼叫會自動收掉交易的 repository 方法。
    """
    sqldb.session.connection().execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": f"twitch_event_response:{twitch_id}"}
    )
    stmt = (
        select(TwitchEventResponse)
        .where(TwitchEventResponse.twitch_id == twitch_id, TwitchEventResponse.event_kind == kind)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return sqldb.session.exec(stmt).one_or_none()


def _finish(twitch_id: int) -> None:
    sqldb.commit()
    cache_invalidation.invalidate("twitch_event_response", str(twitch_id))


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


@_transaction
def save(
    twitch_id: int,
    actor: AuditActor,
    source: AuditSource,
    kind: str,
    enabled: bool,
    template: str,
    verify: Verify | None = None,
) -> EventResponse:
    """設定一種事件的開關與文字。

    開啟且文字與預設相同時等於恢復預設（刪除資料列，之後調整預設文字會一起生效）；
    有效設定沒有變時不寫入也不留紀錄。
    """
    validate(kind, template)
    row = _begin(twitch_id, kind)
    current = _effective(kind, row)
    if verify is not None:
        verify(comparable({"enabled": current.enabled, "template": current.template}))
    reset_to_default = enabled and template == DEFAULTS[kind]
    result = default_response(kind) if reset_to_default else EventResponse(kind, enabled, template, False)
    if (result.enabled, result.template, result.is_default) == (current.enabled, current.template, current.is_default):
        sqldb.session.rollback()
        return current
    if reset_to_default:
        assert row is not None  # 有效設定有變又回到預設，代表原本有資料列
        before = _snapshot(row.enabled, row.template)
        sqldb.session.delete(row)
        sqldb.session.flush()
        record_change(twitch_id, actor, source, "event_response", kind, "delete", before, None)
    elif row is None:
        sqldb.session.add(
            TwitchEventResponse(
                twitch_id=twitch_id, event_kind=kind, enabled=enabled, template=template, updated_at=nowtz()
            )
        )
        sqldb.session.flush()
        record_change(twitch_id, actor, source, "event_response", kind, "create", None, _snapshot(enabled, template))
    else:
        before = _snapshot(row.enabled, row.template)
        row.enabled = enabled
        row.template = template
        row.updated_at = nowtz()
        sqldb.session.flush()
        record_change(twitch_id, actor, source, "event_response", kind, "update", before, _snapshot(enabled, template))
    _finish(twitch_id)
    return result


@_transaction
def reset(
    twitch_id: int, actor: AuditActor, source: AuditSource, kind: str, verify: Verify | None = None
) -> EventResponse:
    """恢復預設：刪除該列。已經是預設時什麼都不做（冪等）。"""
    _check_kind(kind)
    row = _begin(twitch_id, kind)
    if verify is not None:
        current = _effective(kind, row)
        verify(comparable({"enabled": current.enabled, "template": current.template}))
    if row is None:
        sqldb.session.rollback()
        return default_response(kind)
    before = _snapshot(row.enabled, row.template)
    sqldb.session.delete(row)
    sqldb.session.flush()
    record_change(twitch_id, actor, source, "event_response", kind, "delete", before, None)
    _finish(twitch_id)
    return default_response(kind)
