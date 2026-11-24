"""C-02：以真實 PostgreSQL 驗證後台設定如何影響聊天室執法。"""

import asyncio
from importlib import import_module
from importlib.util import find_spec
from inspect import signature
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
from zlib import crc32

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from twitchAPI.chat import Chat, ChatEvent
from twitchAPI.type import TwitchAPIException

from starlib import twitch_audit, twitch_commands, twitch_regulars
from starlib.database import TwitchBotJoinChannel
from starlib.messaging import cache_invalidation
from starServer import twitch_chatbot
from starServer.dashboard import channels, twitch_control
from starServer.twitch_bot import channels as chat_channels
from starServer.twitch_bot import commands, state, viewers
from tests.helpers.dashboard_auth import FRONTEND, make_app, make_twitch_session

ALICE = "2000000961"
MOD = "2000000962"
BOT = "2000000963"
LINK = "分享 abc.com"
BOT_MODERATION = "starServer.twitch_bot.moderation"
EDITABLE = ("enabled", "exempt_level", "params", "notice", "silent")
KINDS = {"link", "blocked_word", "caps", "emote", "symbol", "repetition", "length", "duplicate"}


@pytest.fixture
def channel_id(request):
    return str(2110000000 + crc32(request.node.nodeid.encode()) % 10000000)


@pytest.fixture
def host(monkeypatch, repo, channel_id, dashboard_env):
    for module in (channels, commands, viewers, twitch_audit, twitch_commands, twitch_regulars):
        monkeypatch.setattr(module, "sqldb", repo)
    for name in (
        "starlib.twitch_moderation",
        "starServer.dashboard.channel_moderation",
        "starServer.dashboard.channel_settings",
        BOT_MODERATION,
    ):
        if find_spec(name) is not None:
            module = import_module(name)
            if hasattr(module, "sqldb"):
                monkeypatch.setattr(module, "sqldb", repo)
    repo.add(TwitchBotJoinChannel(twitch_id=int(channel_id), state="enabled"))
    monkeypatch.setattr(cache_invalidation, "invalidate", Mock())
    monkeypatch.setattr(twitch_control, "check_template", AsyncMock(return_value="ok"))
    sid = make_twitch_session(repo, twitch_id=channel_id, login="host", name="Host")
    client = TestClient(
        make_app(), base_url=f"https://testserver/dashboard/channels/{channel_id}/", headers={"Origin": FRONTEND}
    )
    client.cookies.set("dashboard_session", sid)
    return client


def settings(client):
    response = client.get("moderation")
    assert response.status_code == 200, response.text
    return response.json()


def filter_fields(client):
    (link,) = (row for row in settings(client)["filters"] if row["kind"] == "link")
    return {key: link[key] for key in EDITABLE}


def put_filter(client, changes, *, kind="link", original=None):
    if original is None:
        original = filter_fields(client)
    return client.put(f"moderation/filters/{kind}", json={"original": original, "values": {**original, **changes}})


@pytest.fixture
def configure(host):
    def save(**changes):
        response = put_filter(host, {"enabled": True, **changes})
        assert response.is_success, response.text
        return response.json()["filter"]

    return save


def test_新頻道讀取所有關閉的過濾器與預設值(host):
    data = settings(host)
    assert {row["kind"] for row in data["filters"]} == KINDS
    assert all(row["enabled"] is False for row in data["filters"])
    assert data["settings"]["strike_reset_minutes"] == 60
    assert data["settings"]["permit_seconds"] == 60
    assert filter_fields(host) == {
        "enabled": False,
        "exempt_level": "vip",
        "params": {"whitelist": []},
        "notice": None,
        "silent": False,
    }


@pytest.mark.parametrize("level", ["subscriber", "regular", "vip", "mod"])
def test_後台接受四種豁免層級(host, configure, level):
    configure(exempt_level=level)
    assert filter_fields(host)["exempt_level"] == level


def test_後台拒絕無效豁免層級且不寫入(host):
    original = filter_fields(host)
    response = put_filter(host, {"exempt_level": "everyone"}, original=original)
    assert 400 <= response.status_code < 500, response.text
    assert filter_fields(host) == original


def test_後台拒絕未知過濾器(host):
    response = put_filter(host, {"enabled": True}, kind="unknown")
    assert response.status_code == 400, response.text


@pytest.mark.parametrize(("result", "status"), [("blocked", 422), ("unavailable", 503)])
def test_AutoMod_拒絕或無法檢查時保留原告知與開關(host, result, status):
    twitch_control.check_template.return_value = result
    original = filter_fields(host)
    response = put_filter(host, {"enabled": True, "notice": "請遵守聊天室規則"}, original=original)
    assert response.status_code == status, response.text
    assert filter_fields(host) == original


def test_告知沒變更時免檢查_過期編輯收到衝突(host, configure):
    original = filter_fields(host)
    configure(silent=True)
    twitch_control.check_template.assert_not_awaited()
    response = put_filter(host, {"notice": "新告知"}, original=original)
    assert response.status_code == 409, response.text
    assert filter_fields(host)["silent"] is True
    assert filter_fields(host)["notice"] is None


def test_mod_能編輯連結過濾且修改紀錄記下操作者(host, repo, twitch_mods, channel_id):
    twitch_mods.set(channel_id, (MOD, "Mod"))
    client = TestClient(make_app(), base_url=host.base_url, headers={"Origin": FRONTEND})
    sid = make_twitch_session(repo, twitch_id=MOD, session_id="moderation-mod", login="mod", name="Mod")
    client.cookies.set("dashboard_session", sid)
    response = put_filter(client, {"enabled": True, "exempt_level": "regular"})
    assert response.is_success, response.text
    assert filter_fields(host)["enabled"] is True
    (entry,) = host.get("audit").json()["entries"]
    assert (entry["source"], entry["target_kind"], entry["actor"]["name"]) == ("dashboard", "moderation", "Mod")
    assert entry["after"]["enabled"] is True


class ChatStarted(Exception):
    """在開啟 Twitch socket 前中止，以已註冊的 handler 模擬聊天室。"""


class ChatHarness:
    def __init__(self, channel_id):
        self.now = 10_000.0
        self.room = SimpleNamespace(room_id=channel_id, name="host")
        self.events = {}
        self.commands = {}
        self.deletions = []
        self.timeouts = []
        self.notices = []
        self.fail_delete = False

    async def delete(self, broadcaster_id, moderator_id, message_id):
        self.deletions.append((str(broadcaster_id), str(moderator_id), message_id))
        if self.fail_delete:
            raise TwitchAPIException("Twitch refused to delete")

    async def ban(self, broadcaster_id, moderator_id, user_id, reason, duration=None):
        self.timeouts.append((str(broadcaster_id), str(moderator_id), str(user_id), duration))

    async def notice(self, room, text):
        self.notices.append((getattr(room, "name", room), text))

    def send(self, text=LINK, *, uid=ALICE, login="alice", mod=False, vip=False, subscriber=False, emotes=None):
        msg = SimpleNamespace(
            id=uuid4().hex,
            text=text,
            emotes=emotes,
            source_room_id=None,
            room=self.room,
            user=SimpleNamespace(
                id=uid, name=login, display_name=login.title(), mod=mod, vip=vip, subscriber=subscriber
            ),
            reply=AsyncMock(),
        )
        asyncio.run(self.events[ChatEvent.MESSAGE](msg))
        return msg

    def invoke(self, command, parameter):
        assert command in self.commands, f"!{command} 尚未註冊"
        cmd = SimpleNamespace(
            parameter=parameter,
            room=self.room,
            user=SimpleNamespace(id=MOD, name="mod", display_name="Mod", mod=True),
            reply=AsyncMock(),
        )
        asyncio.run(self.commands[command](cmd))
        cmd.reply.assert_awaited_once()
        return cmd.reply.await_args.args[0]


@pytest.fixture
def start_chat(host, monkeypatch, repo, channel_id):
    harness = ChatHarness(channel_id)
    if find_spec(BOT_MODERATION) is not None:
        monkeypatch.setattr(import_module(BOT_MODERATION), "_now", lambda: harness.now)

    async def get_users(*, logins=None, user_ids=None):
        if logins is None and user_ids is None:
            yield SimpleNamespace(id=BOT, login="bot")
        if channel_id in (user_ids or ()):
            yield SimpleNamespace(id=channel_id, login="host", display_name="Host")
        if "alice" in (logins or ()):
            yield SimpleNamespace(id=ALICE, login="alice", display_name="Alice")

    twitch = SimpleNamespace(
        get_users=get_users,
        set_user_authentication=AsyncMock(),
        delete_chat_message=harness.delete,
        ban_user=harness.ban,
    )
    client = SimpleNamespace(
        username="bot",
        send_message=harness.notice,
        register_event=harness.events.__setitem__,
        register_command=harness.commands.__setitem__,
        start=Mock(side_effect=ChatStarted),
    )
    create_chat = AsyncMock(return_value=client)
    monkeypatch.setattr(state, "load_join_channels", Mock())
    monkeypatch.setattr(state, "join_channels", {int(channel_id): repo.get_twitch_join_channel(int(channel_id))})
    monkeypatch.setattr(state, "TARGET_CHANNEL", {int(channel_id): None})
    monkeypatch.setattr(state, "TARGET_CHANNEL_IDS", [channel_id])
    monkeypatch.setattr(chat_channels, "rooms", {})
    for name, value in (("twitch", twitch), ("chat", client), ("bot_user_id", BOT)):
        monkeypatch.setattr(state, name, value, raising=False)
    monkeypatch.setattr(twitch_chatbot, "Twitch", AsyncMock(return_value=twitch))
    monkeypatch.setattr(twitch_chatbot, "Chat", create_chat)
    monkeypatch.setattr(
        twitch_chatbot,
        "sqldb",
        SimpleNamespace(
            get_oauth_client=Mock(return_value=SimpleNamespace(client_id="test", client_secret="test")),
            get_bot_oauth_token=Mock(return_value=SimpleNamespace(access_token="test", refresh_token="test")),
            release_session=Mock(),
        ),
    )

    def start():
        with pytest.raises(ChatStarted):
            asyncio.run(twitch_chatbot.run())
        harness.chat_constructor = signature(Chat).bind(*create_chat.call_args.args, **create_chat.call_args.kwargs)
        harness.chat_constructor.apply_defaults()
        return harness

    return start


def enforcement(repo, channel_id):
    return (
        repo.session.execute(
            text(
                'SELECT at, user_id, user_login, user_name, "filter", strike, action, duration, message, status '
                "FROM stardb_basic.twitch_enforcement_log WHERE twitch_id = :channel ORDER BY id"
            ),
            {"channel": int(channel_id)},
        )
        .mappings()
        .all()
    )


def test_新頻道觀眾貼連結不刪除不禁言(start_chat):
    chat = start_chat()
    chat.send()
    assert chat.deletions == chat.timeouts == chat.notices == []


def test_首次刪除再犯禁言兩次均告知並記錄(configure, start_chat, repo, channel_id):
    configure()
    chat = start_chat()
    first = chat.send()
    chat.now += 11
    second = chat.send("另一則連結 xyz.com")

    assert chat.deletions == [(channel_id, BOT, first.id)]
    assert chat.timeouts == [(channel_id, BOT, ALICE, 600)]
    assert len(chat.notices) == 2
    assert all(room == "host" and "Alice" in message for room, message in chat.notices)
    rows = enforcement(repo, channel_id)
    assert [
        (
            str(row["user_id"]),
            row["user_login"],
            row["user_name"],
            row["filter"],
            row["strike"],
            row["action"],
            row["duration"],
            row["message"],
            row["status"],
        )
        for row in rows
    ] == [
        (ALICE, "alice", "Alice", "link", 1, "delete", None, first.text, "ok"),
        (ALICE, "alice", "Alice", "link", 2, "timeout", 600, second.text, "ok"),
    ]
    assert all(row["at"] is not None for row in rows)


def test_距離上次犯規超過六十分鐘再貼會刪除(configure, start_chat):
    configure()
    chat = start_chat()
    first = chat.send()
    chat.now += 3601
    second = chat.send()
    assert [message_id for _, _, message_id in chat.deletions] == [first.id, second.id]
    assert chat.timeouts == []


def test_VIP_與固定豁免身分可以貼連結但訂閱者會被刪除(configure, start_chat, channel_id):
    configure()
    chat = start_chat()
    chat.send(uid="2000000964", vip=True)
    chat.send(uid=channel_id, login="host")
    chat.send(uid=MOD, login="mod", mod=True)
    chat.send(uid=BOT, login="bot")
    subscriber = chat.send(subscriber=True)
    assert chat.deletions == [(channel_id, BOT, subscriber.id)]
    assert chat.timeouts == []


def test_常客豁免後被_mod_移除就會執法(configure, start_chat, channel_id):
    # 使用真正註冊的聊天室常客指令，讓常客快取隨修改更新。
    configure(exempt_level="regular")
    chat = start_chat()
    chat.invoke("regular", "add alice")
    chat.send()
    assert chat.deletions == []
    chat.invoke("regular", "remove alice")
    msg = chat.send()
    assert chat.deletions == [(channel_id, BOT, msg.id)]


@pytest.mark.parametrize("target", ["alice", "@alice"])
def test_mod_放行後六十秒內可分享_逾時後執法(configure, start_chat, channel_id, target):
    configure()
    chat = start_chat()
    chat.invoke("permit", target)
    chat.now += 59
    chat.send()
    assert chat.deletions == []
    chat.now += 2
    msg = chat.send()
    assert chat.deletions == [(channel_id, BOT, msg.id)]


def test_mod_無法放行不存在帳號或在關閉協作時放行(configure, start_chat, host, channel_id):
    configure()
    chat = start_chat()
    assert "找不到" in chat.invoke("permit", "unknown")
    assert host.put("mod-collab", json={"enabled": False}).is_success
    assert "權限不足" in chat.invoke("permit", "alice")
    msg = chat.send()
    assert chat.deletions == [(channel_id, BOT, msg.id)]


def test_Chat_啟用_TwitchAPI_的_Shared_Chat_來源過濾(start_chat):
    chat = start_chat()
    assert chat.chat_constructor.arguments["no_shared_chat_messages"] is True


@pytest.mark.parametrize("entry", ["https://www.youtube.com/", "youtube.com"])
def test_後台正規化白名單且_bot_套用(configure, start_chat, host, channel_id, entry):
    saved = configure(params={"whitelist": [entry]})
    assert saved["params"]["whitelist"] == ["youtube.com"]
    assert filter_fields(host)["params"]["whitelist"] == ["youtube.com"]
    chat = start_chat()
    chat.send("https://m.youtube.com/watch")
    blocked = chat.send()
    assert chat.deletions == [(channel_id, BOT, blocked.id)]


def test_靜音仍刪除違規並留下紀錄(configure, start_chat, repo, channel_id):
    configure(silent=True)
    chat = start_chat()
    msg = chat.send()
    assert chat.deletions == [(channel_id, BOT, msg.id)]
    assert chat.notices == []
    assert len(enforcement(repo, channel_id)) == 1


def test_五名觀眾十秒內犯規全數執法但只送一次自訂告知(configure, start_chat, repo, channel_id):
    configure(notice="{user}｜{filter}")
    chat = start_chat()
    for i in range(5):
        chat.now += 1
        chat.send(uid=str(int(ALICE) + 10 + i))
    assert len(chat.deletions) == 5
    assert len(enforcement(repo, channel_id)) == 5
    ((_, notice),) = chat.notices
    assert notice.startswith("Alice｜")
    assert notice.removeprefix("Alice｜").strip() not in ("", "{filter}")
    twitch_control.check_template.assert_awaited_once()


def test_自訂指令帶違規連結會被刪除且不回應(configure, start_chat, host, repo, monkeypatch, channel_id):
    configure()
    saved = host.post("commands", json={"name": "hi", "response": "Hello", "global_cooldown": 0, "user_cooldown": 0})
    assert saved.is_success, saved.text
    repo.cache.twitch_cmd.load(repo.get_raw_chat_command_all())
    say = AsyncMock(return_value=True)
    monkeypatch.setattr(commands.speech, "say", say)
    chat = start_chat()
    chat.send("!hi")
    say.assert_awaited_once()
    say.reset_mock()

    msg = chat.send("!hi abc.com")
    assert chat.deletions == [(channel_id, BOT, msg.id)]
    say.assert_not_awaited()


def test_Twitch_執法失敗會記錄失敗且下一次仍只刪除(configure, start_chat, repo, channel_id):
    configure()
    chat = start_chat()
    chat.fail_delete = True
    first = chat.send()
    assert chat.deletions == [(channel_id, BOT, first.id)]
    assert chat.notices == []
    (failed,) = enforcement(repo, channel_id)
    assert (failed["status"], failed["message"], failed["action"]) == ("failed", first.text, "delete")
    chat.fail_delete = False
    second = chat.send()
    assert chat.deletions[-1] == (channel_id, BOT, second.id)
    assert chat.timeouts == []
    assert len(chat.notices) == 1
    assert [(row["status"], row["strike"]) for row in enforcement(repo, channel_id)] == [("failed", 1), ("ok", 1)]
