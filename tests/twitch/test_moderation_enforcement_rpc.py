"""C-06：Twitch bot 端的 `moderation.lift` 與 `moderation.clear_strikes` RPC。

handler 在 `twitch_chatbot.run()` 完成設定時以 `rpc.handle` 註冊（與 `channel.sync` 同一時機），測試從那裡取出。
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from twitchAPI import twitch as sdk
from twitchAPI.type import AuthScope

from starlib.messaging import rpc
from starServer.twitch_bot import state
from starServer.twitch_bot.helix import BotTwitch
from tests.dashboard.test_channel_moderation import (
    ALICE,
    BOT,
    EDITABLE,
    channel_id,  # noqa: F401 (fixture)
    configure,  # noqa: F401 (fixture)
    host,  # noqa: F401 (fixture)
    put_filter,
    settings,
    start_chat,  # noqa: F401 (fixture)
)

BOB = "2000000965"


@pytest.fixture
def handlers(monkeypatch):
    registered = {}

    def handle(method, handler, *_args, **_kwargs):
        registered[method] = handler

    monkeypatch.setattr(rpc, "handle", handle)
    return registered


def call(handlers, method, payload):
    assert method in handlers, f"{method} 尚未註冊"
    return asyncio.run(handlers[method](payload))


# ---- moderation.clear_strikes ----


def test_清除犯規次數後該觀眾所有過濾器回到第一段且不影響其他觀眾(host, configure, start_chat, handlers, channel_id):
    configure()
    # 連結以外再開一個過濾器，驗證「所有過濾器」
    (blocked,) = (row for row in settings(host)["filters"] if row["kind"] == "blocked_word")
    original = {key: blocked[key] for key in EDITABLE}
    changes = {"enabled": True, "params": {**blocked["params"], "words": ["禁字"]}}
    assert put_filter(host, changes, kind="blocked_word", original=original).is_success
    chat = start_chat()

    chat.send()  # alice 連結第 1 次：刪除
    chat.send("禁字", uid=ALICE)  # alice 禁字第 1 次：刪除
    chat.send(uid=BOB, login="bob")  # bob 連結第 1 次：刪除
    assert chat.timeouts == []

    call(handlers, "moderation.clear_strikes", {"twitch_id": int(channel_id), "user_id": int(ALICE)})
    chat.send()
    chat.send("禁字", uid=ALICE)
    assert chat.timeouts == []  # 兩個過濾器都回到第 1 段（刪除）

    chat.send(uid=BOB, login="bob")
    assert [(user, duration) for _, _, user, duration in chat.timeouts] == [(BOB, 600)]  # bob 沒被清除，進入第 2 段


# ---- moderation.lift ----


@pytest.fixture
def helix(monkeypatch):
    """真的 BotTwitch，Helix 回應在 HTTP 層替身。"""
    request = AsyncMock()

    class Session:
        def __init__(self, **_options):
            pass

        async def __aenter__(self):
            return SimpleNamespace(request=request)

        async def __aexit__(self, *_exc):
            pass

    monkeypatch.setattr(sdk, "ClientSession", Session)
    client = BotTwitch("test-client", authenticate_app=False)
    asyncio.run(
        client.set_user_authentication(
            "test-token", [AuthScope.MODERATOR_MANAGE_BANNED_USERS], "test-refresh", validate=False
        )
    )
    client.auto_refresh_auth = False
    monkeypatch.setattr(state, "twitch", client, raising=False)
    monkeypatch.setattr(state, "bot_user_id", BOT, raising=False)
    return request


def helix_response(status, body=None):
    return SimpleNamespace(status=status, headers={"Ratelimit-Reset": "0"}, json=AsyncMock(return_value=body or {}))


def test_解除處罰以_Helix_unban_並回_lifted(helix, handlers, start_chat, channel_id):
    start_chat()
    helix.return_value = helix_response(204)

    result = call(handlers, "moderation.lift", {"twitch_id": int(channel_id), "user_id": int(ALICE)})

    assert result == {"result": "lifted"}
    ((method, url), kwargs) = (helix.call_args.args[:2], helix.call_args.kwargs)
    assert (method, "moderation/bans" in url) == ("DELETE", True)
    sent = f"{url} {kwargs}"
    assert all(value in sent for value in (channel_id, BOT, ALICE))


@pytest.mark.parametrize(("status", "result"), [(400, "not_punished"), (403, "not_mod")])
def test_Helix_400_視為不在處罰中_403_視為_bot_不是_mod(helix, handlers, start_chat, channel_id, status, result):
    start_chat()
    helix.return_value = helix_response(status, {"error": "x", "status": status, "message": "x"})
    assert call(handlers, "moderation.lift", {"twitch_id": int(channel_id), "user_id": int(ALICE)}) == {
        "result": result
    }


@pytest.mark.parametrize("status", [500, 429])
def test_其他_Twitch_失敗拋錯讓後台顯示失敗(helix, handlers, start_chat, channel_id, status):
    start_chat()
    helix.return_value = helix_response(status, {"error": "x", "status": status, "message": "x"})
    assert "moderation.lift" in handlers
    with pytest.raises(Exception):  # noqa: B017 失敗型別由實作決定，只要求不回成功
        call(handlers, "moderation.lift", {"twitch_id": int(channel_id), "user_id": int(ALICE)})
