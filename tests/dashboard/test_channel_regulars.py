"""C-01 從後台與聊天室維護同一份常客名單。"""

import asyncio
import re
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from zlib import crc32

import httpx
import pytest
from fastapi.testclient import TestClient

from starlib import twitch_audit, twitch_commands, twitch_tokens
from starlib.database import TwitchBotJoinChannel
from starlib.messaging import cache_invalidation
from starServer import twitch_chatbot
from starServer.dashboard import channel_settings, channels, twitch_control
from starServer.twitch_bot import commands, state
from tests.helpers.dashboard_auth import FRONTEND, make_app, make_twitch_session

pytestmark = pytest.mark.usefixtures("dashboard_env")

ALICE = "2000000902"
BOB = "2000000903"
MOD = "2000000904"

USERS = {
    "alice": {"id": ALICE, "login": "alice", "display_name": "Alice"},
    "bob": {"id": BOB, "login": "bob", "display_name": "Bob"},
}


@pytest.fixture
def channel_id(request):
    return 2100000000 + crc32(request.node.nodeid.encode()) % 10000000


@pytest.fixture
def host(monkeypatch, repo, channel_id):
    for module in (channel_settings, channels, commands, twitch_audit, twitch_commands):
        monkeypatch.setattr(module, "sqldb", repo)
    for name in ("starlib.twitch_regulars", "starServer.dashboard.channel_regulars", "starServer.twitch_bot.viewers"):
        module = sys.modules.get(name)
        if module is not None and hasattr(module, "sqldb"):
            monkeypatch.setattr(module, "sqldb", repo)
    repo.add(TwitchBotJoinChannel(twitch_id=channel_id, state="enabled"))
    monkeypatch.setattr(cache_invalidation, "invalidate", Mock())
    monkeypatch.setattr(twitch_tokens, "broadcaster_token_blocking", lambda _: "test-broadcaster-token")
    monkeypatch.setattr(twitch_control, "check_template", AsyncMock(return_value="ok"))

    async def helix_send(_client, request, **_kwargs):
        assert (request.method, request.url.host, request.url.path) == ("GET", "api.twitch.tv", "/helix/users")
        user = USERS.get(request.url.params["login"])
        return httpx.Response(200, json={"data": [user] if user else []}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "send", helix_send)
    session = make_twitch_session(repo, twitch_id=str(channel_id), login="host", name="Host")
    client = TestClient(
        make_app(), base_url=f"https://testserver/dashboard/channels/{channel_id}/", headers={"Origin": FRONTEND}
    )
    client.cookies.set("dashboard_session", session)
    return client


def regular_ids(host):
    response = host.get("regulars")
    assert response.status_code == 200, response.text
    return {str(row["user_id"]) for row in response.json()["regulars"]}


def test_後台新增後名單出現並能以帳號_ID_移除(host):
    response = host.post("regulars", json={"login": "alice"})
    assert response.is_success, response.text
    assert regular_ids(host) == {ALICE}
    (entry,) = host.get("audit").json()["entries"]
    assert (entry["source"], entry["target_kind"], entry["action"]) == (
        "dashboard",
        "regular",
        "create",
    )

    response = host.delete(f"regulars/{ALICE}")
    assert response.is_success, response.text
    assert regular_ids(host) == set()


def test_後台找不到帳號回_404_且不新增(host):
    response = host.post("regulars", json={"login": "unknown"})
    assert response.status_code == 404
    assert response.json()["error"] == "user_not_found"
    assert regular_ids(host) == set()


def test_後台重複新增回_409_且只留一筆(host):
    assert host.post("regulars", json={"login": "alice"}).is_success
    response = host.post("regulars", json={"login": "alice"})
    assert response.status_code == 409
    assert response.json()["error"] == "already_regular"
    assert len(host.get("regulars").json()["regulars"]) == 1


def test_後台能將自訂指令儲存為常客專用(host):
    response = host.post("commands", json={"name": "hi", "response": "Hello", "permission": "regular"})
    assert response.is_success, response.text
    (command,) = host.get("commands").json()["commands"]
    assert command["permission"] == "regular"


class ChatRegistered(Exception):
    """在公開指令完成註冊後中止啟動，避免建立 WebSocket。"""


@pytest.fixture
def chat_command(host, monkeypatch, channel_id):
    async def get_users(*, logins=None, user_ids=None):
        if logins is None and user_ids is None:
            yield SimpleNamespace(id="1", login="bot")
        for login in logins or ():
            if login in USERS:
                yield SimpleNamespace(**USERS[login])

    twitch = SimpleNamespace(get_users=get_users, set_user_authentication=AsyncMock())
    registered = {}
    chat = SimpleNamespace(
        register_event=Mock(),
        register_command=lambda name, callback: registered.update({name: callback}),
        start=Mock(side_effect=ChatRegistered),
    )
    monkeypatch.setattr(state, "load_join_channels", Mock())
    monkeypatch.setattr(state, "TARGET_CHANNEL_IDS", [])
    monkeypatch.setattr(state, "twitch", twitch, raising=False)
    monkeypatch.setattr(state, "chat", chat, raising=False)
    monkeypatch.setattr(twitch_chatbot, "Twitch", AsyncMock(return_value=twitch))
    monkeypatch.setattr(twitch_chatbot, "Chat", AsyncMock(return_value=chat))
    monkeypatch.setattr(
        twitch_chatbot,
        "sqldb",
        SimpleNamespace(
            get_oauth_client=Mock(return_value=SimpleNamespace(client_id="test", client_secret="test")),
            get_bot_oauth_token=Mock(return_value=SimpleNamespace(access_token="test", refresh_token="test")),
            release_session=Mock(),
        ),
    )
    with pytest.raises(ChatRegistered):
        asyncio.run(twitch_chatbot.run())

    def invoke(parameter, *, mod=True):
        cmd = SimpleNamespace(
            parameter=parameter,
            room=SimpleNamespace(room_id=str(channel_id), name="host"),
            user=SimpleNamespace(id=MOD, name="mod", display_name="Mod", mod=mod),
            reply=AsyncMock(),
        )
        assert "regular" in registered, "!regular 尚未註冊"
        asyncio.run(registered["regular"](cmd))
        return cmd.reply

    return invoke


def test_mod_在聊天室加入與移除會更新後台名單及修改紀錄(host, chat_command):
    chat_command("add @alice").assert_awaited_once()
    assert regular_ids(host) == {ALICE}

    chat_command("remove alice").assert_awaited_once()
    assert regular_ids(host) == set()
    entries = host.get("audit").json()["entries"]
    assert {(entry["source"], entry["target_kind"], entry["action"]) for entry in entries} == {
        ("chat", "regular", "create"),
        ("chat", "regular", "delete"),
    }


@pytest.mark.parametrize(
    ("parameter", "expected", "initially_regular"),
    [("add alice", "已(?:經)?是.*常客", True), ("remove bob", "不是.*常客", False), ("add unknown", "找不到", False)],
)
def test_聊天室照實回覆重複加入_移除非成員_找不到帳號(host, chat_command, parameter, expected, initially_regular):
    if initially_regular:
        chat_command("add alice")
    reply = chat_command(parameter)
    reply.assert_awaited_once()
    assert re.search(expected, reply.await_args.args[0])
    assert regular_ids(host) == ({ALICE} if initially_regular else set())


def test_關閉_mod_協作時聊天室拒絕新增(host, chat_command):
    assert host.put("mod-collab", json={"enabled": False}).is_success
    reply = chat_command("add alice")
    reply.assert_awaited_once()
    assert "權限不足" in reply.await_args.args[0]
    assert regular_ids(host) == set()


def test_一般觀眾使用常客管理指令沒有反應(host, chat_command):
    chat_command("add alice", mod=False).assert_not_awaited()
    assert regular_ids(host) == set()


def test_加入後下一則訊息立即適用常客權限且改名仍能用(host, chat_command, monkeypatch, repo, channel_id):
    for name, permission in (("rhi", "regular"), ("shi", "subscriber")):
        response = host.post(
            "commands",
            json={"name": name, "response": "Hello", "permission": permission, "global_cooldown": 0},
        )
        assert response.is_success, response.text
    repo.cache.twitch_cmd.load(repo.get_raw_chat_command_all())
    say = AsyncMock(return_value=True)
    monkeypatch.setattr(commands.speech, "say", say)

    def trigger(text, uid, login, *, vip=False, subscriber=False):
        say.reset_mock()
        msg = SimpleNamespace(
            text=text,
            room=SimpleNamespace(room_id=str(channel_id), name="host"),
            user=SimpleNamespace(id=uid, name=login, display_name=login, mod=False, vip=vip, subscriber=subscriber),
            reply=AsyncMock(),
        )
        asyncio.run(commands.respond_to_chat_command(msg))
        return say.await_count

    assert trigger("!rhi", ALICE, "alice") == 0
    chat_command("add @alice")
    assert trigger("!rhi", ALICE, "alice") == 1
    assert trigger("!rhi", ALICE, "alice_renamed") == 1
    assert trigger("!shi", ALICE, "alice_renamed") == 1
    assert trigger("!rhi", BOB, "bob", vip=True) == 1
    assert trigger("!rhi", BOB, "bob", subscriber=True) == 0
    assert trigger("!rhi", BOB, "bob") == 0
    assert regular_ids(host) == {ALICE}
