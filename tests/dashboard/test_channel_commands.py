"""實況主後台的自訂指令端點（W-05）：清單、新增、編輯、刪除、編輯衝突、AutoMod 與未啟用時唯讀（真實 PostgreSQL，測完 rollback）。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from starlib import twitch_audit, twitch_commands
from starlib.database import TwitchBotJoinChannel
from starlib.messaging import cache_invalidation
from starlib.twitch_audit import list_changes
from starServer.dashboard import channels, twitch_control
from starServer.twitch_bot import commands as bot_commands
from tests.helpers.dashboard_auth import FRONTEND, make_app, make_twitch_session

pytestmark = pytest.mark.usefixtures("dashboard_env")

CHANNEL_ID = 2000000081
URL = f"/dashboard/channels/{CHANNEL_ID}/commands"
HEADERS = {"Origin": FRONTEND}


@pytest.fixture(autouse=True)
def _env(monkeypatch, repo):
    for module in (channels, twitch_commands, twitch_audit, bot_commands):
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
    return {
        "name": "hi",
        "response": "hello",
        "aliases": [],
        "enabled": True,
        "global_cooldown": 30,
        "user_cooldown": 0,
        "permission": "everyone",
        **kw,
    }


def post(client, **kw):
    return client.post(URL, json=values(**kw), headers=HEADERS)


def put(client, name, new, original):
    return client.put(f"{URL}/{name}", json={"values": new, "original": original}, headers=HEADERS)


def delete(client, name, original):
    return client.request("DELETE", f"{URL}/{name}", json={"original": original}, headers=HEADERS)


def original_of(command: dict) -> dict:
    return {k: command[k] for k in values()}


# ── 清單與新增 ──


def test_清單只有自己的頻道且依名稱排序(client, repo):
    post(client, name="b")
    post(client, name="a")
    twitch_commands.create(
        CHANNEL_ID + 1, twitch_audit.AuditActor("twitch", "1", "x"), "chat", "other", twitch_commands.CommandFields("x")
    )
    r = client.get(URL)
    assert r.status_code == 200
    assert [c["name"] for c in r.json()["commands"]] == ["a", "b"]
    assert set(r.json()["commands"][0]) == {*values(), "use_count", "updated_at"}


def test_其他頻道的指令端點是_403(client):
    assert client.get(f"/dashboard/channels/{CHANNEL_ID + 5}/commands").status_code == 403
    r = client.post(f"/dashboard/channels/{CHANNEL_ID + 5}/commands", json=values(), headers=HEADERS)
    assert (r.status_code, r.json()["error"]) == (403, "channel_forbidden")


def test_新增後有紀錄_通知_bot_且立即能觸發(client, repo, invalidated, monkeypatch):
    r = post(client, name="Hi", response="哈囉 {user}", aliases=["H"], permission="mod", global_cooldown=5)
    assert r.status_code == 200
    command = r.json()["command"]
    assert (command["name"], command["aliases"], command["permission"], command["use_count"]) == ("hi", ["h"], "mod", 0)
    assert invalidated == [("twitch_cmd", str(CHANNEL_ID))]
    [entry] = list_changes(CHANNEL_ID)
    assert (entry.source, entry.action, entry.actor.platform, entry.actor.id) == (
        "dashboard",
        "create",
        "twitch",
        str(CHANNEL_ID),
    )
    # bot 收到失效通知後，用別名在聊天室觸發
    repo.cache.twitch_cmd.load({})  # bot 啟動時已載入過快取
    bot_commands._reload(str(CHANNEL_ID))
    monkeypatch.setattr(bot_commands.speech, "say", AsyncMock(return_value=True))
    user = SimpleNamespace(id=str(CHANNEL_ID), name="host", display_name="Host", mod=False, vip=False, subscriber=False)
    msg = SimpleNamespace(text="!h", room=SimpleNamespace(room_id=str(CHANNEL_ID), name="host"), user=user)
    asyncio.run(bot_commands.respond_to_chat_command(msg))
    assert bot_commands.speech.say.await_args.args[2] == "哈囉 {user}"


def test_聊天室新增的指令後台看得到_來源是聊天室(client, repo, monkeypatch):
    monkeypatch.setattr(bot_commands, "check_template", AsyncMock(return_value="ok"))
    chatter = SimpleNamespace(id="5", name="mod", display_name="Mod", mod=True)
    cmd = SimpleNamespace(
        parameter="yo 你好", room=SimpleNamespace(room_id=str(CHANNEL_ID), name="host"), user=chatter, reply=AsyncMock()
    )
    asyncio.run(bot_commands.add_chat_command(cmd))
    assert [c["name"] for c in client.get(URL).json()["commands"]] == ["yo"]
    assert list_changes(CHANNEL_ID)[0].source == "chat"


@pytest.mark.parametrize(
    ("kw", "field"),
    [
        ({"name": ""}, "name"),
        ({"name": "add_cmd"}, "name"),
        ({"name": "edit_cmd"}, "name"),
        ({"aliases": ["hi"]}, "aliases"),
        ({"aliases": ["list_cmd"]}, "aliases"),
        ({"response": "a" * 501}, "response"),
        ({"global_cooldown": 3601}, "global_cooldown"),
        ({"permission": "god"}, "permission"),
    ],
)
def test_欄位不合法回_invalid_field(client, kw, field):
    r = post(client, **kw)
    assert (r.status_code, r.json()["error"], r.json()["field"]) == (400, "invalid_field", field)
    assert r.json()["reason"]
    twitch_control.check_template.assert_not_awaited()  # 擋在 AutoMod 檢查之前


def test_名稱或別名重複標出欄位(client):
    post(client, name="hi", aliases=["h"])
    for kw, field in (
        ({"name": "hi"}, "name"),
        ({"name": "h"}, "name"),
        ({"name": "x", "aliases": ["hi"]}, "aliases"),
        ({"name": "x", "aliases": ["h"]}, "aliases"),
    ):
        r = post(client, **kw)
        assert (r.status_code, r.json()["error"], r.json()["field"]) == (400, "invalid_field", field)
    assert len(client.get(URL).json()["commands"]) == 1


def test_邊界值可以儲存(client):
    r = post(client, name="a" * 25, response="a" * 500, global_cooldown=0, user_cooldown=3600)
    assert r.status_code == 200


@pytest.mark.parametrize(
    ("result", "status", "code"), [("blocked", 422, "automod_blocked"), ("unavailable", 503, "automod_unavailable")]
)
def test_AutoMod_擋下或無法檢查時不儲存(client, result, status, code):
    twitch_control.check_template.return_value = result
    r = post(client, response="壞話")
    assert (r.status_code, r.json()["error"]) == (status, code)
    assert client.get(URL).json()["commands"] == []
    assert list_changes(CHANNEL_ID) == []


# ── 編輯 ──


def test_編輯回應時檢查_AutoMod_只改開關時不檢查(client):
    command = post(client).json()["command"]
    twitch_control.check_template.reset_mock()
    r = put(client, "hi", values(enabled=False), original_of(command))
    assert r.status_code == 200 and r.json()["command"]["enabled"] is False
    twitch_control.check_template.assert_not_awaited()
    twitch_control.check_template.return_value = "blocked"
    r = put(client, "hi", values(enabled=False, response="壞話"), original_of(r.json()["command"]))
    assert (r.status_code, r.json()["error"]) == (422, "automod_blocked")


def test_編輯記前後值_觸發指令不造成假衝突(client, repo):
    command = post(client).json()["command"]
    repo.increment_twitch_cmd_use_count(CHANNEL_ID, "hi")  # 聊天室觸發了指令
    r = put(client, "hi", values(response="bye", permission="vip"), original_of(command))
    assert r.status_code == 200
    assert r.json()["command"]["use_count"] == 1
    entry = list_changes(CHANNEL_ID)[0]
    assert (entry.action, entry.before["response"], entry.after["response"], entry.after["permission"]) == (
        "update",
        "hello",
        "bye",
        "vip",
    )


def test_後台編輯中聊天室改了同一個指令_儲存時回_409(client, repo, monkeypatch):
    command = post(client).json()["command"]
    monkeypatch.setattr(bot_commands, "check_template", AsyncMock(return_value="ok"))
    mod = SimpleNamespace(id="5", name="mod", display_name="Mod", mod=True)
    chat = SimpleNamespace(
        parameter="hi 聊天室改的",
        room=SimpleNamespace(room_id=str(CHANNEL_ID), name="host"),
        user=mod,
        reply=AsyncMock(),
    )
    asyncio.run(bot_commands.edit_chat_command(chat))

    r = put(client, "hi", values(response="後台改的"), original_of(command))

    assert r.status_code == 409
    body = r.json()
    assert (body["error"], body["deleted"]) == ("conflict", False)
    assert body["current"]["response"] == "聊天室改的"
    assert twitch_commands.find(CHANNEL_ID, "hi").response == "聊天室改的"
    # 以最新值當原始值再送一次就能覆蓋
    r = put(client, "hi", values(response="後台改的"), {**original_of(command), "response": "聊天室改的"})
    assert r.status_code == 200 and r.json()["command"]["response"] == "後台改的"


def test_編輯已被刪除的指令回_409_deleted(client):
    command = post(client).json()["command"]
    twitch_commands.delete(CHANNEL_ID, twitch_audit.AuditActor("twitch", "5", "mod"), "chat", "hi")
    r = put(client, "hi", values(response="x"), original_of(command))
    assert (r.status_code, r.json()["error"], r.json()["deleted"], r.json()["current"]) == (409, "conflict", True, None)


def test_改名保留使用次數_紀錄一次_update(client, repo):
    command = post(client).json()["command"]
    repo.increment_twitch_cmd_use_count(CHANNEL_ID, "hi")
    r = put(client, "hi", values(name="Hello"), original_of(command))
    assert r.status_code == 200
    assert (r.json()["command"]["name"], r.json()["command"]["use_count"]) == ("hello", 1)
    assert [c["name"] for c in client.get(URL).json()["commands"]] == ["hello"]
    entries = list_changes(CHANNEL_ID)
    assert [(e.action, e.target_key) for e in entries] == [("update", "hello"), ("create", "hi")]


def test_改名撞到別的指令回_invalid_field(client):
    post(client, name="a")
    command = post(client, name="b").json()["command"]
    r = put(client, "b", values(name="a"), original_of(command))
    assert (r.status_code, r.json()["field"]) == (400, "name")


# ── 刪除 ──


def test_刪除連別名並留紀錄(client, invalidated):
    command = post(client, aliases=["h"]).json()["command"]
    invalidated.clear()
    r = delete(client, "hi", original_of(command))
    assert r.status_code == 200
    assert client.get(URL).json()["commands"] == []
    assert invalidated == [("twitch_cmd", str(CHANNEL_ID))]
    assert (list_changes(CHANNEL_ID)[0].action, list_changes(CHANNEL_ID)[0].after) == ("delete", None)


def test_刪除時資料已被改過回_409_不刪(client):
    command = post(client).json()["command"]
    put(client, "hi", values(response="別人改的"), original_of(command))
    r = delete(client, "hi", original_of(command))
    assert (r.status_code, r.json()["error"], r.json()["deleted"]) == (409, "conflict", False)
    assert len(client.get(URL).json()["commands"]) == 1


def test_刪除已被刪除的指令回_409_deleted(client):
    command = post(client).json()["command"]
    delete(client, "hi", original_of(command))
    r = delete(client, "hi", original_of(command))
    assert (r.status_code, r.json()["deleted"]) == (409, True)


# ── 未啟用時唯讀 ──


@pytest.mark.parametrize("state", ["inactive", "disabled"])
def test_bot_沒有啟用時清單照常_修改回_409(client, repo, state):
    command = post(client).json()["command"]
    row = repo.session.get(TwitchBotJoinChannel, CHANNEL_ID)
    row.state = state
    repo.session.flush()

    assert [c["name"] for c in client.get(URL).json()["commands"]] == ["hi"]
    for response in (
        post(client, name="x"),
        put(client, "hi", values(response="x"), original_of(command)),
        delete(client, "hi", original_of(command)),
    ):
        assert (response.status_code, response.json()["error"]) == (409, "channel_not_enabled")
    assert twitch_commands.find(CHANNEL_ID, "hi").response == "hello"


def test_頻道還沒有列時也是唯讀(client, repo):
    repo.session.delete(repo.session.get(TwitchBotJoinChannel, CHANNEL_ID))
    repo.session.flush()
    assert post(client).json()["error"] == "channel_not_enabled"
    assert client.get(URL).status_code == 200
