"""聊天室執法紀錄的查詢、處置標記與到期清除。同步函式，由呼叫端放在 DB worker thread 上執行。"""

from datetime import timedelta

from sqlalchemy import delete
from sqlmodel import Session, col, select

from starlib.database import TwitchEnforcementLog, sqldb
from starlib.twitch_audit import AuditActor, record_change
from starlib.utils import nowtz

#: 後台每頁的筆數
PAGE_SIZE = 50
#: 紀錄保留的天數，查詢與清除都以此為界
RETENTION_DAYS = 30


def _cutoff():
    return nowtz() - timedelta(days=RETENTION_DAYS)


def list_page(session: Session, twitch_id: int, offset: int = 0) -> list[TwitchEnforcementLog]:
    """頻道 30 天內的執法紀錄，新的在前，從第 offset 筆起最多 PAGE_SIZE 筆。session 由呼叫端提供。"""
    stmt = (
        select(TwitchEnforcementLog)
        .where(TwitchEnforcementLog.twitch_id == twitch_id, TwitchEnforcementLog.at >= _cutoff())
        .order_by(col(TwitchEnforcementLog.at).desc(), col(TwitchEnforcementLog.id).desc())
        .offset(max(offset, 0))
        .limit(PAGE_SIZE)
        .execution_options(populate_existing=True)
    )
    return list(session.exec(stmt).all())


def get(twitch_id: int, log_id: int) -> TwitchEnforcementLog | None:
    """頻道的某筆執法紀錄；不存在、屬於別的頻道或已超過保留期限都回 None。"""
    row = sqldb.session.get(TwitchEnforcementLog, log_id, populate_existing=True)
    if row is None or row.twitch_id != twitch_id or row.at < _cutoff():
        return None
    return row


def is_active_punishment(row: TwitchEnforcementLog) -> bool:
    """這筆紀錄的處罰還可能在生效：是 timeout 或 ban、還沒解除，timeout 還沒到期。"""
    if row.action not in ("timeout", "ban") or row.lifted_at is not None:
        return False
    return row.action == "ban" or row.at + timedelta(seconds=row.duration or 0) > nowtz()


def _commit_change(twitch_id: int, actor: AuditActor, log_id: int, before: dict | None, after: dict) -> None:
    record_change(twitch_id, actor, "dashboard", "enforcement", str(log_id), "update", before, after)
    sqldb.commit()


def mark_lifted(twitch_id: int, log_id: int, actor: AuditActor) -> None:
    """標示已解除並記一筆 `enforcement` 修改紀錄，同一個交易提交。"""
    try:
        row = sqldb.session.get(TwitchEnforcementLog, log_id, populate_existing=True)
        if row is None or row.twitch_id != twitch_id:
            return
        row.lifted_at = nowtz()
        who = {"user_id": row.user_id, "user_login": row.user_login}
        _commit_change(
            twitch_id, actor, log_id, {"lifted_at": None, **who}, {"lifted_at": row.lifted_at.isoformat(), **who}
        )
    except BaseException:
        sqldb.session.rollback()
        raise


def record_clear_strikes(twitch_id: int, log_id: int, actor: AuditActor, user_id: int, user_login: str) -> None:
    """記一筆清除犯規次數的 `enforcement` 修改紀錄。"""
    try:
        _commit_change(
            twitch_id,
            actor,
            log_id,
            None,
            {"clear_strikes": True, "user_id": user_id, "user_login": user_login},
        )
    except BaseException:
        sqldb.session.rollback()
        raise


def purge_expired() -> int:
    """刪除超過保留期限的紀錄，回傳刪除筆數。"""
    try:
        result = sqldb.session.execute(delete(TwitchEnforcementLog).where(col(TwitchEnforcementLog.at) < _cutoff()))
        sqldb.commit()
        return result.rowcount
    except BaseException:
        sqldb.session.rollback()
        raise
    finally:
        sqldb.release_session()
