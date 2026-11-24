"""Twitch Blocked Terms 的修改紀錄。詞本身在 Twitch，這裡只記後台的新增與刪除。同步函式，由呼叫端放在 DB worker thread 上執行。"""

from starlib.database import sqldb
from starlib.twitch_audit import AuditActor, record_change


def record_added(twitch_id: int, actor: AuditActor, term_id: str, text: str) -> None:
    """記一筆 `blocked_term` 新增。"""
    _commit(twitch_id, actor, term_id, "create", None, {"text": text})


def record_removed(twitch_id: int, actor: AuditActor, term_id: str, text: str | None) -> None:
    """記一筆 `blocked_term` 刪除；詞已不在清單上、查不到文字時只記 id。"""
    _commit(twitch_id, actor, term_id, "delete", {"text": text} if text is not None else {}, None)


def _commit(twitch_id: int, actor: AuditActor, term_id: str, action, before: dict | None, after: dict | None) -> None:
    try:
        record_change(twitch_id, actor, "dashboard", "blocked_term", term_id, action, before, after)
        sqldb.commit()
    except BaseException:
        sqldb.session.rollback()
        raise
