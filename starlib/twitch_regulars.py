"""Twitch 常客的查詢與寫入。同步函式，由呼叫端放在 DB worker thread 上執行。"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import text
from sqlmodel import select

from starlib.database import TwitchRegular, sqldb
from starlib.messaging import cache_invalidation
from starlib.twitch_audit import AuditActor, AuditSource, record_change


def list_regulars(twitch_id: int | None = None) -> list[TwitchRegular]:
    """讀取單一頻道的常客，或在 bot 載入快取時讀取所有頻道。"""
    stmt = select(TwitchRegular).order_by(TwitchRegular.user_login, TwitchRegular.user_id)
    if twitch_id is not None:
        stmt = stmt.where(TwitchRegular.twitch_id == twitch_id)
    return list(sqldb.session.exec(stmt.execution_options(populate_existing=True)).all())


def is_regular(twitch_id: int, user_id: int) -> bool:
    return sqldb.session.get(TwitchRegular, (twitch_id, user_id), populate_existing=True) is not None


@contextmanager
def _transaction(twitch_id: int) -> Iterator[None]:
    """序列化同頻道名單的修改，常客資料和 audit 在同一交易內提交。"""
    try:
        sqldb.session.connection().execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": f"twitch_regular:{twitch_id}"}
        )
        yield
        sqldb.commit()
    except BaseException:
        sqldb.session.rollback()
        raise


def add(twitch_id: int, actor: AuditActor, source: AuditSource, user_id: int, login: str, name: str) -> bool:
    with _transaction(twitch_id):
        if is_regular(twitch_id, user_id):
            return False
        sqldb.session.add(TwitchRegular(twitch_id=twitch_id, user_id=user_id, user_login=login, user_name=name))
        record_change(
            twitch_id, actor, source, "regular", str(user_id), "create", None,
            {"user_login": login, "user_name": name},
        )
    cache_invalidation.invalidate("twitch_regular", str(twitch_id))
    return True


def remove(twitch_id: int, actor: AuditActor, source: AuditSource, user_id: int) -> bool:
    with _transaction(twitch_id):
        row = sqldb.session.get(TwitchRegular, (twitch_id, user_id), populate_existing=True)
        if row is None:
            return False
        record_change(
            twitch_id, actor, source, "regular", str(user_id), "delete",
            {"user_login": row.user_login, "user_name": row.user_name}, None,
        )
        sqldb.session.delete(row)
    cache_invalidation.invalidate("twitch_regular", str(twitch_id))
    return True
