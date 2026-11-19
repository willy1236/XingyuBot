"""實況主後台的事件回應端點（W-07）：清單、設定、恢復預設、編輯衝突、AutoMod 與未啟用時唯讀（真實 PostgreSQL，測完 rollback）。"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from starlib import twitch_audit, twitch_event_responses
from starlib.database import TwitchBotJoinChannel
from starlib.messaging import cache_invalidation
from starlib.twitch_audit import list_changes
from starServer.dashboard import channels, twitch_control
from tests.helpers.dashboard_auth import FRONTEND, make_app, make_twitch_session

pytestmark = pytest.mark.usefixtures("dashboard_env")

CHANNEL_ID = 2000000091
URL = f"/dashboard/channels/{CHANNEL_ID}/event-responses"
HEADERS = {"Origin": FRONTEND}
DEFAULT_FOLLOW = twitch_event_responses.DEFAULTS["follow"]


@pytest.fixture(autouse=True)
def _env(monkeypatch, repo):
    for module in (channels, twitch_event_responses, twitch_audit):
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


def values(enabled=True, template="歡迎 {user}") -> dict:
    return {"enabled": enabled, "template": template}


DEFAULT = values(template=DEFAULT_FOLLOW)


def put(client, kind="follow", new=None, original=None):
    body = {"values": new or values(), "original": original or DEFAULT}
    return client.put(f"{URL}/{kind}", json=body, headers=HEADERS)


def delete(client, kind="follow", original=None):
    return client.request("DELETE", f"{URL}/{kind}", json={"original": original or DEFAULT}, headers=HEADERS)


def rows(client) -> dict:
    return {r["kind"]: r for r in client.get(URL).json()["event_responses"]}


def test_沒設定過時六種預設開啟_附可用變數(client):
    r = client.get(URL)
    assert r.status_code == 200
    items = r.json()["event_responses"]
    assert [i["kind"] for i in items] == list(twitch_event_responses.KINDS)
    assert all(i["enabled"] and i["is_default"] for i in items)
    assert [v["token"] for v in rows(client)["gift"]["variables"]] == ["{user}", "{amount}", "{channel}"]


def test_其他頻道的端點是_403(client):
    other = f"/dashboard/channels/{CHANNEL_ID + 5}/event-responses"
    assert client.get(other).status_code == 403
    r = client.put(f"{other}/follow", json={"values": values(), "original": DEFAULT}, headers=HEADERS)
    assert (r.status_code, r.json()["error"]) == (403, "channel_forbidden")


def test_設定後有紀錄_通知_bot(client, invalidated):
    r = put(client)
    assert r.status_code == 200
    assert r.json()["event_response"]["is_default"] is False
    assert rows(client)["follow"]["template"] == "歡迎 {user}"
    assert invalidated == [("twitch_event_response", str(CHANNEL_ID))]
    [entry] = list_changes(CHANNEL_ID)
    assert (entry.source, entry.action, entry.target_kind, entry.target_key) == (
        "dashboard",
        "create",
        "event_response",
        "follow",
    )
    assert (entry.actor.platform, entry.actor.id) == ("twitch", str(CHANNEL_ID))


def test_恢復預設刪列並留紀錄(client):
    put(client)
    r = delete(client, original=values())
    assert r.status_code == 200 and r.json()["event_response"]["is_default"] is True
    assert rows(client)["follow"]["is_default"]
    assert list_changes(CHANNEL_ID)[0].action == "delete"
    assert delete(client).status_code == 200  # 已是預設，冪等


def test_文字改回預設等於恢復預設(client):
    put(client)
    r = put(client, new=DEFAULT, original=values())
    assert r.status_code == 200 and r.json()["event_response"]["is_default"] is True


@pytest.mark.parametrize("template", ["", "a" * 501])
def test_文字不合法回_invalid_field(client, template):
    r = put(client, new=values(template=template))
    assert (r.status_code, r.json()["error"], r.json()["field"]) == (400, "invalid_field", "template")
    twitch_control.check_template.assert_not_awaited()  # 擋在 AutoMod 檢查之前


def test_不認得的事件種類回_404(client):
    assert put(client, kind="nope").status_code == 404
    assert delete(client, kind="nope").json()["error"] == "event_kind_not_found"


def test_AutoMod_擋下或無法檢查時不儲存(client):
    twitch_control.check_template.return_value = "blocked"
    r = put(client)
    assert (r.status_code, r.json()["error"]) == (422, "automod_blocked")
    twitch_control.check_template.return_value = "unavailable"
    r = put(client)
    assert (r.status_code, r.json()["error"]) == (503, "automod_unavailable")
    assert rows(client)["follow"]["is_default"] and list_changes(CHANNEL_ID) == []


def test_只切換開關或用預設文字不花_AutoMod_額度(client):
    twitch_control.check_template.return_value = "unavailable"
    assert put(client, new=values(enabled=False, template=DEFAULT_FOLLOW)).status_code == 200
    assert put(client, new=DEFAULT, original=values(enabled=False, template=DEFAULT_FOLLOW)).status_code == 200
    twitch_control.check_template.assert_not_awaited()


def test_後台編輯時別處改了同一種事件_回_409_不覆蓋(client):
    put(client)
    r = put(client, new=values(template="我的版本"), original=DEFAULT)
    assert r.status_code == 409
    assert r.json()["deleted"] is False
    assert r.json()["current"] == {"enabled": "true", "response": "歡迎 {user}"}
    assert rows(client)["follow"]["template"] == "歡迎 {user}"
    assert delete(client).status_code == 409


def test_以有效值比對_已是預設時原始值是預設不算衝突(client):
    put(client)
    delete(client, original=values())
    assert put(client, new=values(template="新的")).status_code == 200


def test_頻道沒啟用時唯讀(client, repo):
    channel = repo.session.get(TwitchBotJoinChannel, CHANNEL_ID)
    channel.state = "disabled"
    repo.session.flush()
    assert client.get(URL).status_code == 200
    for r in (put(client), delete(client)):
        assert (r.status_code, r.json()["error"]) == (409, "channel_not_enabled")
