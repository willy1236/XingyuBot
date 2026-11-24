"""實況資訊（標題、分類）的修改紀錄。標題與分類存在 Twitch，這裡只記後台的修改。同步函式，由呼叫端放在 DB worker thread 上執行。"""

from starlib.database import sqldb
from starlib.twitch_audit import AuditActor, record_change

#: 後台一次修改標題與分類，只記一筆，target_key 固定
TARGET_KEY = "stream"


def record_updated(twitch_id: int, actor: AuditActor, before: dict, after: dict) -> None:
    """記一筆 `stream_info` 修改；before、after 是 `{title, game, game_id}`。"""
    try:
        record_change(twitch_id, actor, "dashboard", "stream_info", TARGET_KEY, "update", before, after)
        sqldb.commit()
    except BaseException:
        sqldb.session.rollback()
        raise
