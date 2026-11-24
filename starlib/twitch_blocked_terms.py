"""Twitch Blocked Terms 的修改紀錄。詞本身在 Twitch，這裡只記後台的新增與刪除。同步函式，由呼叫端放在 DB worker thread 上執行。"""

from starlib.database import sqldb
from starlib.twitch_audit import AuditActor, record_change


def term_problem(text: str) -> str | None:
    if len(text) > 500:
        return "詞最多 500 字"
    minimum = 3 if "*" in text else 2
    if sum(not char.isspace() and char != "*" for char in text) < minimum:
        return f"詞至少需要 {minimum} 個非空白、非萬用字元"
    if any("*" in word.strip("*") for word in text.split()):
        return "萬用字元 * 必須放在字詞開頭或結尾"
    return None


def record_added(twitch_id: int, actor: AuditActor, term_id: str, text: str) -> None:
    """記一筆 `blocked_term` 新增。"""
    _commit(twitch_id, actor, term_id, "create", None, {"text": text})


def record_removed(twitch_id: int, actor: AuditActor, term_id: str, text: str) -> None:
    """記一筆 `blocked_term` 刪除。"""
    _commit(twitch_id, actor, term_id, "delete", {"text": text}, None)


def _commit(twitch_id: int, actor: AuditActor, term_id: str, action, before: dict | None, after: dict | None) -> None:
    try:
        record_change(twitch_id, actor, "dashboard", "blocked_term", term_id, action, before, after)
        sqldb.commit()
    except BaseException:
        sqldb.session.rollback()
        raise
