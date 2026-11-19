"""實況主後台的計時訊息端點（W-06）：清單、新增、編輯、刪除、編輯衝突、數量上限、AutoMod 與未啟用時唯讀（真實 PostgreSQL，測完 rollback）。"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from starlib import twitch_audit, twitch_timers
from starlib.database import TwitchBotJoinChannel
from starlib.messaging import cache_invalidation
from starlib.twitch_audit import AuditActor, list_changes
from starlib.twitch_timers import TIMERS_MAX, TimerFields
from starServer.dashboard import channels, twitch_control
from tests.helpers.dashboard_auth import FRONTEND, make_app, make_twitch_session

pytestmark = pytest.mark.usefixtures("dashboard_env")

CHANNEL_ID = 2000000082
URL = f"/dashboard/channels/{CHANNEL_ID}/timers"
HEADERS = {"Origin": FRONTEND}


@pytest.fixture(autouse=True)
def _env(monkeypatch, repo):
    for module in (channels, twitch_timers, twitch_audit):
        monkeypatch.setattr(module, "sqldb", repo)
    existing = repo.session.get(TwitchBotJoinChannel, CHANNEL_ID)
    if existing is not None:
        repo.session.delete(existing)
        repo.session.flush()
    repo.add(TwitchBotJoinChannel(twitch_id=CHANNEL_ID, state="enabled"))
    invalidated: list[tuple[str, str | None]] = []
    monkeypatch.setattr(cache_invalidation, "invalidate", lambda cache, key=None, **_: invalidated.append((cache, key)))
    monkeypatch.setattr(twitch_control, "check_template", AsyncMock(return_value="ok"))
    return invalidated


@pytest.fixture
def invalidated(_env):
    return _env


@pytest.fixture
def client(repo) -> TestClient:
    sid = make_twitch_session(repo, twitch_id=str(CHANNEL_ID), login="host", name="Host")
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
    c.cookies.set("dashboard_session", sid)
    return c


def values(**kw) -> dict:
    return {"message": "記得追隨", "interval_minutes": 10, "min_chat_lines": 0, "enabled": True, **kw}


def post(client, **kw):
    return client.post(URL, json=values(**kw), headers=HEADERS)


def put(client, timer_id, new, original):
    return client.put(f"{URL}/{timer_id}", json={"values": new, "original": original}, headers=HEADERS)


def delete(client, timer_id, original):
    return client.request("DELETE", f"{URL}/{timer_id}", json={"original": original}, headers=HEADERS)


def original_of(timer: dict) -> dict:
    return {k: timer[k] for k in values()}


# ── 清單與新增 ──


def test_清單只有自己的頻道且依_id_排序(client):
    first = post(client, message="a").json()["timer"]
    second = post(client, message="b").json()["timer"]
    twitch_timers.create(CHANNEL_ID + 1, AuditActor("twitch", "1", "x"), TimerFields("別人的", 5))
    r = client.get(URL)
    assert r.status_code == 200
    assert [t["id"] for t in r.json()["timers"]] == [first["id"], second["id"]]
    assert set(r.json()["timers"][0]) == {"id", *values(), "updated_at"}


def test_其他頻道的計時訊息端點是_403(client):
    other = f"/dashboard/channels/{CHANNEL_ID + 5}/timers"
    assert client.get(other).status_code == 403
    r = client.post(other, json=values(), headers=HEADERS)
    assert (r.status_code, r.json()["error"]) == (403, "channel_forbidden")


def test_新增後有紀錄並通知_bot(client, invalidated):
    r = post(client, min_chat_lines=10)
    assert r.status_code == 200
    timer = r.json()["timer"]
    assert (timer["message"], timer["interval_minutes"], timer["min_chat_lines"], timer["enabled"]) == (
        "記得追隨",
        10,
        10,
        True,
    )
    assert invalidated == [("twitch_timer", str(CHANNEL_ID))]
    [entry] = list_changes(CHANNEL_ID)
    assert (entry.source, entry.action, entry.target_kind, entry.target_key) == (
        "dashboard",
        "create",
        "timer",
        str(timer["id"]),
    )
    assert (entry.actor.platform, entry.actor.id) == ("twitch", str(CHANNEL_ID))


@pytest.mark.parametrize(
    ("kw", "field"),
    [
        ({"message": ""}, "message"),
        ({"message": "a" * 501}, "message"),
        ({"interval_minutes": 4}, "interval_minutes"),
        ({"interval_minutes": 1441}, "interval_minutes"),
        ({"min_chat_lines": -1}, "min_chat_lines"),
        ({"min_chat_lines": 1001}, "min_chat_lines"),
    ],
)
def test_欄位不合法回_invalid_field(client, kw, field):
    r = post(client, **kw)
    assert (r.status_code, r.json()["error"], r.json()["field"]) == (400, "invalid_field", field)
    assert r.json()["reason"]
    twitch_control.check_template.assert_not_awaited()  # 擋在 AutoMod 檢查之前
    assert client.get(URL).json()["timers"] == []


def test_邊界值可以儲存(client):
    assert post(client, message="a" * 500, interval_minutes=5, min_chat_lines=0).status_code == 200
    assert post(client, interval_minutes=1440, min_chat_lines=1000).status_code == 200


def test_達到數量上限後新增回_invalid_field_limit(client, invalidated):
    for i in range(TIMERS_MAX):
        assert post(client, message=f"m{i}").status_code == 200
    invalidated.clear()
    r = post(client, message="第 21 則")
    assert (r.status_code, r.json()["error"], r.json()["field"]) == (400, "invalid_field", "limit")
    assert len(client.get(URL).json()["timers"]) == TIMERS_MAX
    assert invalidated == []


def test_達到上限仍可編輯與刪除_刪除後可再新增(client):
    timers = [post(client, message=f"m{i}").json()["timer"] for i in range(TIMERS_MAX)]
    assert put(client, timers[0]["id"], values(message="m0", enabled=False), original_of(timers[0])).status_code == 200
    assert delete(client, timers[1]["id"], original_of(timers[1])).status_code == 200
    assert post(client, message="補上").status_code == 200


@pytest.mark.parametrize(
    ("result", "status", "code"), [("blocked", 422, "automod_blocked"), ("unavailable", 503, "automod_unavailable")]
)
def test_AutoMod_擋下或無法檢查時不儲存(client, result, status, code):
    twitch_control.check_template.return_value = result
    r = post(client, message="壞話")
    assert (r.status_code, r.json()["error"]) == (status, code)
    assert client.get(URL).json()["timers"] == []
    assert list_changes(CHANNEL_ID) == []


# ── 編輯 ──


def test_編輯訊息時檢查_AutoMod_只改開關或間隔時不檢查(client):
    timer = post(client).json()["timer"]
    twitch_control.check_template.reset_mock()
    r = put(client, timer["id"], values(enabled=False, interval_minutes=30), original_of(timer))
    assert r.status_code == 200 and r.json()["timer"]["enabled"] is False
    twitch_control.check_template.assert_not_awaited()
    twitch_control.check_template.return_value = "blocked"
    r = put(client, timer["id"], values(message="壞話"), original_of(r.json()["timer"]))
    assert (r.status_code, r.json()["error"]) == (422, "automod_blocked")


def test_編輯記前後值並通知(client, invalidated):
    timer = post(client).json()["timer"]
    invalidated.clear()
    r = put(client, timer["id"], values(message="新訊息", interval_minutes=60, min_chat_lines=5), original_of(timer))
    assert r.status_code == 200
    assert invalidated == [("twitch_timer", str(CHANNEL_ID))]
    entry = list_changes(CHANNEL_ID)[0]
    assert (entry.action, entry.before["message"], entry.after["message"], entry.after["interval_minutes"]) == (
        "update",
        "記得追隨",
        "新訊息",
        60,
    )


def test_編輯沒有變更時不留紀錄也不通知(client, invalidated):
    timer = post(client).json()["timer"]
    invalidated.clear()
    r = put(client, timer["id"], values(), original_of(timer))
    assert r.status_code == 200
    assert r.json()["timer"] == timer
    assert [e.action for e in list_changes(CHANNEL_ID)] == ["create"]
    assert invalidated == []


def test_編輯時資料已被改過回_409_且不寫入(client):
    timer = post(client).json()["timer"]
    put(client, timer["id"], values(message="別人改的"), original_of(timer))
    r = put(client, timer["id"], values(message="我改的"), original_of(timer))
    assert r.status_code == 409
    assert (r.json()["error"], r.json()["deleted"], r.json()["current"]["message"]) == ("conflict", False, "別人改的")
    assert client.get(URL).json()["timers"][0]["message"] == "別人改的"
    # 以最新值當原始值再送一次就能覆蓋
    r = put(client, timer["id"], values(message="我改的"), {**original_of(timer), "message": "別人改的"})
    assert r.status_code == 200 and r.json()["timer"]["message"] == "我改的"


def test_編輯已被刪除的計時訊息回_409_deleted(client):
    timer = post(client).json()["timer"]
    twitch_timers.delete(CHANNEL_ID, AuditActor("twitch", "5", "mod"), timer["id"])
    r = put(client, timer["id"], values(message="x"), original_of(timer))
    assert (r.status_code, r.json()["error"], r.json()["deleted"], r.json()["current"]) == (409, "conflict", True, None)


def test_編輯別的頻道的計時訊息回_409_deleted(client):
    other = twitch_timers.create(CHANNEL_ID + 1, AuditActor("twitch", "1", "x"), TimerFields("別人的", 5))
    r = put(client, other.id, values(), values())
    assert (r.status_code, r.json()["deleted"]) == (409, True)
    assert twitch_timers.list_timers(CHANNEL_ID + 1)[0].message == "別人的"


# ── 刪除 ──


def test_刪除留紀錄並通知(client, invalidated):
    timer = post(client).json()["timer"]
    invalidated.clear()
    assert delete(client, timer["id"], original_of(timer)).status_code == 200
    assert client.get(URL).json()["timers"] == []
    assert invalidated == [("twitch_timer", str(CHANNEL_ID))]
    entry = list_changes(CHANNEL_ID)[0]
    assert (entry.action, entry.after, entry.before["message"]) == ("delete", None, "記得追隨")


def test_刪除時資料已被改過回_409_不刪(client):
    timer = post(client).json()["timer"]
    put(client, timer["id"], values(message="別人改的"), original_of(timer))
    r = delete(client, timer["id"], original_of(timer))
    assert (r.status_code, r.json()["error"], r.json()["deleted"]) == (409, "conflict", False)
    assert len(client.get(URL).json()["timers"]) == 1


def test_刪除已被刪除的計時訊息回_409_deleted(client):
    timer = post(client).json()["timer"]
    delete(client, timer["id"], original_of(timer))
    r = delete(client, timer["id"], original_of(timer))
    assert (r.status_code, r.json()["deleted"]) == (409, True)


# ── 未啟用時唯讀 ──


@pytest.mark.parametrize("state", ["inactive", "disabled"])
def test_bot_沒有啟用時清單照常_修改回_409(client, repo, state):
    timer = post(client).json()["timer"]
    row = repo.session.get(TwitchBotJoinChannel, CHANNEL_ID)
    row.state = state
    repo.session.flush()

    assert [t["id"] for t in client.get(URL).json()["timers"]] == [timer["id"]]
    for response in (
        post(client, message="x"),
        put(client, timer["id"], values(message="x"), original_of(timer)),
        delete(client, timer["id"], original_of(timer)),
    ):
        assert (response.status_code, response.json()["error"]) == (409, "channel_not_enabled")
    assert twitch_timers.list_timers(CHANNEL_ID)[0].message == "記得追隨"


def test_頻道還沒有列時也是唯讀(client, repo):
    repo.session.delete(repo.session.get(TwitchBotJoinChannel, CHANNEL_ID))
    repo.session.flush()
    assert post(client).json()["error"] == "channel_not_enabled"
    assert client.get(URL).status_code == 200
