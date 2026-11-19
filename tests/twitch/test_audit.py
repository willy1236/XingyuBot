"""starlib.twitch_audit：修改紀錄的寫入與查詢。寫進綁在外層交易的 repo，測完 rollback；不動全域 sqldb 的 session，免得別的測試留在裡面的物件過期。"""

import pytest

from starlib import twitch_audit
from starlib.twitch_audit import AuditActor, list_changes, record_change

TWITCH_ID = 2000000021
ACTOR = AuditActor("twitch", "1234", "streamer")


@pytest.fixture(autouse=True)
def session(monkeypatch, repo):
    monkeypatch.setattr(twitch_audit, "sqldb", repo)
    return repo.session


def test_寫入後查得到操作者_時間_來源_前後():
    record_change(TWITCH_ID, ACTOR, "dashboard", "command", "hi", "update", {"response": "a"}, {"response": "b"})
    [entry] = list_changes(TWITCH_ID)
    assert entry.actor == ACTOR
    assert (entry.source, entry.target_kind, entry.target_key, entry.action) == ("dashboard", "command", "hi", "update")
    assert (entry.before, entry.after) == ({"response": "a"}, {"response": "b"})
    assert entry.at is not None


def test_新增沒有_before_刪除沒有_after():
    record_change(TWITCH_ID, ACTOR, "chat", "command", "hi", "create", None, {"response": "a"})
    record_change(TWITCH_ID, ACTOR, "chat", "command", "hi", "delete", {"response": "a"}, None)
    entries = list_changes(TWITCH_ID)
    assert [e.action for e in entries] == ["delete", "create"]  # 新的在前
    assert entries[0].after is None and entries[1].before is None


def test_析域帳號操作者寫入後原樣查回():
    actor = AuditActor("domalyze", "6f1c2a9e-0000-4000-8000-000000000001", "willy")
    record_change(TWITCH_ID, actor, "dashboard", "command", "hi", "create", None, {"response": "a"})
    [entry] = list_changes(TWITCH_ID)
    assert entry.actor == actor


def test_不_commit_所以_rollback_後不見(session):
    record_change(TWITCH_ID, ACTOR, "dashboard", "timer", "1", "create", None, {"message": "m"})
    assert len(list_changes(TWITCH_ID)) == 1  # 同一個 session 看得到
    session.rollback()
    assert list_changes(TWITCH_ID) == []


def test_分頁與只看該頻道():
    for i in range(5):
        record_change(TWITCH_ID, ACTOR, "dashboard", "timer", str(i), "create", None, {})
    record_change(TWITCH_ID + 1, ACTOR, "dashboard", "timer", "x", "create", None, {})
    assert [e.target_key for e in list_changes(TWITCH_ID, offset=1, limit=2)] == ["3", "2"]
    assert len(list_changes(TWITCH_ID)) == 5
