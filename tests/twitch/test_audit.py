"""starlib.twitch_audit：修改紀錄的寫入與查詢。用全域 sqldb，測試資料用獨有的 twitch_id，結束後刪除。"""

import pytest
from sqlmodel import delete

from starlib.database import TwitchChannelAudit, sqldb
from starlib.twitch_audit import AuditActor, list_changes, record_change

TWITCH_ID = 2000000021
ACTOR = AuditActor("twitch", "1234", "streamer")


@pytest.fixture(autouse=True)
def _clean():
    yield
    sqldb.session.rollback()
    sqldb.session.exec(delete(TwitchChannelAudit).where(TwitchChannelAudit.twitch_id == TWITCH_ID))
    sqldb.session.commit()
    sqldb.release_session()


def test_寫入後查得到操作者_時間_來源_前後():
    record_change(TWITCH_ID, ACTOR, "dashboard", "command", "hi", "update", {"response": "a"}, {"response": "b"})
    sqldb.session.commit()
    [entry] = list_changes(TWITCH_ID)
    assert entry.actor == ACTOR
    assert (entry.source, entry.target_kind, entry.target_key, entry.action) == ("dashboard", "command", "hi", "update")
    assert (entry.before, entry.after) == ({"response": "a"}, {"response": "b"})
    assert entry.at is not None


def test_新增沒有_before_刪除沒有_after():
    record_change(TWITCH_ID, ACTOR, "chat", "command", "hi", "create", None, {"response": "a"})
    record_change(TWITCH_ID, ACTOR, "chat", "command", "hi", "delete", {"response": "a"}, None)
    sqldb.session.commit()
    entries = list_changes(TWITCH_ID)
    assert [e.action for e in entries] == ["delete", "create"]  # 新的在前
    assert entries[0].after is None and entries[1].before is None


def test_不_commit_所以_rollback_後不見():
    record_change(TWITCH_ID, ACTOR, "dashboard", "timer", "1", "create", None, {"message": "m"})
    assert len(list_changes(TWITCH_ID)) == 1  # 同一個 session 看得到
    sqldb.session.rollback()
    assert list_changes(TWITCH_ID) == []


def test_分頁與只看該頻道():
    for i in range(5):
        record_change(TWITCH_ID, ACTOR, "dashboard", "timer", str(i), "create", None, {})
    record_change(TWITCH_ID + 1, ACTOR, "dashboard", "timer", "x", "create", None, {})
    sqldb.session.commit()
    try:
        assert [e.target_key for e in list_changes(TWITCH_ID, offset=1, limit=2)] == ["3", "2"]
        assert len(list_changes(TWITCH_ID)) == 5
    finally:
        sqldb.session.exec(delete(TwitchChannelAudit).where(TwitchChannelAudit.twitch_id == TWITCH_ID + 1))
        sqldb.session.commit()
