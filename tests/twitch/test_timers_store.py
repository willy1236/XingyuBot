"""starlib.twitch_timers：計時訊息的驗證與寫入（真實 PostgreSQL，綁外層交易，測完 rollback）。"""

import pytest

from starlib import twitch_audit, twitch_timers
from starlib.messaging import cache_invalidation
from starlib.twitch_audit import AuditActor, list_changes
from starlib.twitch_timers import TIMERS_MAX, TimerFields, TimerInvalid, TimerMissing

TWITCH_ID = 2000000062
ACTOR = AuditActor("twitch", "1", "streamer")


@pytest.fixture(autouse=True)
def _env(monkeypatch, repo):
    monkeypatch.setattr(twitch_timers, "sqldb", repo)
    monkeypatch.setattr(twitch_audit, "sqldb", repo)
    invalidated: list[tuple[str, str | None]] = []
    monkeypatch.setattr(cache_invalidation, "invalidate", lambda cache, key=None, **_: invalidated.append((cache, key)))
    return invalidated


@pytest.fixture
def invalidated(_env):
    return _env


def make(message="追隨喔", interval=10, **kwargs):
    return twitch_timers.create(TWITCH_ID, ACTOR, TimerFields(message, interval, **kwargs))


def test_新增後有紀錄_有預設值_並通知_bot(invalidated):
    row = make()
    assert (row.enabled, row.min_chat_lines, row.interval_minutes) == (True, 0, 10)
    [entry] = list_changes(TWITCH_ID)
    assert (entry.action, entry.target_kind, entry.target_key, entry.source) == (
        "create",
        "timer",
        str(row.id),
        "dashboard",
    )
    assert entry.before is None
    assert entry.after == {"message": "追隨喔", "interval_minutes": 10, "min_chat_lines": 0, "enabled": True}
    assert invalidated == [("twitch_timer", str(TWITCH_ID))]


@pytest.mark.parametrize(
    ("kw", "field"),
    [
        ({"message": ""}, "message"),
        ({"message": "   "}, "message"),
        ({"message": "a" * 501}, "message"),
        ({"interval": 4}, "interval_minutes"),
        ({"interval": 1441}, "interval_minutes"),
        ({"min_chat_lines": -1}, "min_chat_lines"),
        ({"min_chat_lines": 1001}, "min_chat_lines"),
    ],
)
def test_格式與範圍不合法(kw, field, invalidated):
    with pytest.raises(TimerInvalid) as e:
        make(**kw)
    assert e.value.field == field
    assert list_changes(TWITCH_ID) == []
    assert invalidated == []


def test_邊界值可以儲存():
    make("a" * 500, 5, min_chat_lines=0)
    make("b", 1440, min_chat_lines=1000)
    assert len(twitch_timers.list_timers(TWITCH_ID)) == 2


def test_每個頻道最多_20_則_其他頻道不受影響(invalidated):
    for i in range(TIMERS_MAX):
        make(f"m{i}")
    with pytest.raises(TimerInvalid) as e:
        make("第 21 則")
    assert e.value.field == "limit"
    assert len(twitch_timers.list_timers(TWITCH_ID)) == TIMERS_MAX
    assert len(list_changes(TWITCH_ID, 0, 100)) == TIMERS_MAX  # 被拒絕的不留紀錄
    twitch_timers.create(TWITCH_ID + 1, ACTOR, TimerFields("別的頻道", 5))


def test_刪除後可以再新增(invalidated):
    rows = [make(f"m{i}") for i in range(TIMERS_MAX)]
    twitch_timers.delete(TWITCH_ID, ACTOR, rows[0].id)
    make("補上")
    assert len(twitch_timers.list_timers(TWITCH_ID)) == TIMERS_MAX


def test_編輯後紀錄前後值_並通知(invalidated):
    row = make()
    twitch_timers.update(TWITCH_ID, ACTOR, row.id, TimerFields("新訊息", 30, 5, False))
    [entry, _] = list_changes(TWITCH_ID)
    assert entry.action == "update"
    assert entry.before["message"] == "追隨喔" and entry.after == {
        "message": "新訊息",
        "interval_minutes": 30,
        "min_chat_lines": 5,
        "enabled": False,
    }
    assert invalidated[-1] == ("twitch_timer", str(TWITCH_ID))


def test_編輯沒有變更時不寫入_不留紀錄_不通知(invalidated):
    row = make()
    updated_at = row.updated_at
    invalidated.clear()
    result = twitch_timers.update(TWITCH_ID, ACTOR, row.id, TimerFields("追隨喔", 10))
    assert result.updated_at == updated_at
    assert [e.action for e in list_changes(TWITCH_ID)] == ["create"]
    assert invalidated == []


def test_編輯與刪除不存在的計時訊息():
    with pytest.raises(TimerMissing):
        twitch_timers.update(TWITCH_ID, ACTOR, 999999999, TimerFields("x", 5))
    with pytest.raises(TimerMissing):
        twitch_timers.delete(TWITCH_ID, ACTOR, 999999999)


def test_看不到也改不到別的頻道的計時訊息():
    row = twitch_timers.create(TWITCH_ID + 1, ACTOR, TimerFields("別人的", 5))
    assert twitch_timers.list_timers(TWITCH_ID) == []
    with pytest.raises(TimerMissing):
        twitch_timers.update(TWITCH_ID, ACTOR, row.id, TimerFields("x", 5))
    with pytest.raises(TimerMissing):
        twitch_timers.delete(TWITCH_ID, ACTOR, row.id)


def test_刪除記錄修改前的值_after_為空(invalidated):
    row = make()
    twitch_timers.delete(TWITCH_ID, ACTOR, row.id)
    [entry, _] = list_changes(TWITCH_ID)
    assert (entry.action, entry.after) == ("delete", None)
    assert entry.before["message"] == "追隨喔"
    assert twitch_timers.list_timers(TWITCH_ID) == []


def test_verify_拒絕時不寫入也不通知(invalidated):
    row = make()
    invalidated.clear()

    def verify(current):
        raise RuntimeError("conflict")

    with pytest.raises(RuntimeError):
        twitch_timers.update(TWITCH_ID, ACTOR, row.id, TimerFields("改", 5), verify)
    assert twitch_timers.list_timers(TWITCH_ID)[0].message == "追隨喔"
    assert invalidated == []


def test_comparable_是字串形式():
    assert twitch_timers.comparable(
        {"message": "m", "interval_minutes": 10, "min_chat_lines": 0, "enabled": False}
    ) == {
        "message": "m",
        "interval_minutes": "10",
        "min_chat_lines": "0",
        "enabled": "false",
    }
