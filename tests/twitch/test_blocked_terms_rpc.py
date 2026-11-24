"""C-07：Twitch bot 端的 `blocked_terms.list`、`blocked_terms.add`、`blocked_terms.remove` RPC。

handler 在 `twitch_chatbot.run()` 完成設定時以 `rpc.handle` 註冊（與 C-06 的 `moderation.lift` 同一時機）。
Helix 在 HTTP 層以有狀態的替身取代，真的 `BotTwitch` 走完 SDK；RPC 回傳的形狀卡片只定了 `{error: "not_mod"}`，
其餘只驗證行為：Twitch 上的清單變了，以及回傳內容帶得出詞與 id。
"""

import asyncio
import itertools
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import pytest
from twitchAPI import twitch as sdk
from twitchAPI.type import AuthScope

from starlib.messaging import rpc
from starServer.twitch_bot import state
from starServer.twitch_bot.helix import BotTwitch
from tests.dashboard.test_channel_moderation import (
    BOT,
    channel_id,  # noqa: F401 (fixture)
    host,  # noqa: F401 (fixture)
    start_chat,  # noqa: F401 (fixture)
)

SCOPES = [AuthScope.MODERATOR_READ_BLOCKED_TERMS, AuthScope.MODERATOR_MANAGE_BLOCKED_TERMS]


class StubTwitch:
    """Helix `moderation/blocked_terms` 的替身：頻道的詞存在記憶體，可模擬 bot 不是 mod 或其他失敗。"""

    def __init__(self):
        self.terms: dict[str, str] = {}
        self.requests: list[tuple[str, str, dict]] = []
        self.status: int | None = None  # 不為 None 時所有請求都回這個狀態
        self._ids = itertools.count(1)

    def _term(self, term_id, text, channel_id):
        return {
            "broadcaster_id": channel_id,
            "moderator_id": BOT,
            "id": term_id,
            "text": text,
            "created_at": "2026-11-24T00:00:00Z",
            "updated_at": "2026-11-24T00:00:00Z",
            "expires_at": None,
        }

    async def request(self, method, url, **kwargs):
        query = {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}
        query.update(kwargs.get("params") or {})
        body = kwargs.get("json") or {}
        self.requests.append((method, url, {**query, **body}))
        channel_id = str(query.get("broadcaster_id", ""))
        if self.status is not None:
            payload = {"error": "x", "status": self.status, "message": "x"}
            return SimpleNamespace(status=self.status, headers={"Ratelimit-Reset": "0"}, json=AsyncMock(return_value=payload))
        if method == "GET":
            data = [self._term(term_id, text, channel_id) for term_id, text in self.terms.items()]
            return self._ok(200, {"data": data, "pagination": {}})
        if method == "POST":
            term_id = f"term-{next(self._ids)}"
            self.terms[term_id] = body["text"]
            return self._ok(200, {"data": [self._term(term_id, body["text"], channel_id)]})
        self.terms.pop(query["id"], None)
        return self._ok(204, {})

    @staticmethod
    def _ok(status, payload):
        return SimpleNamespace(status=status, headers={"Ratelimit-Reset": "0"}, json=AsyncMock(return_value=payload))

    def sent_texts(self, method):
        return [params.get("text") for m, _, params in self.requests if m == method]

    def removed_ids(self):
        return [params["id"] for m, _, params in self.requests if m == "DELETE"]


@pytest.fixture
def handlers(monkeypatch):
    registered = {}

    def handle(method, handler, *_args, **_kwargs):
        registered[method] = handler

    monkeypatch.setattr(rpc, "handle", handle)
    return registered


@pytest.fixture
def helix(monkeypatch, start_chat, handlers):
    """已啟動聊天室、`state.twitch` 換成走 Helix 替身的真 BotTwitch；回傳替身與 handler 表。"""
    stub = StubTwitch()

    class Session:
        def __init__(self, **_options):
            pass

        async def __aenter__(self):
            return SimpleNamespace(request=stub.request)

        async def __aexit__(self, *_exc):
            pass

    monkeypatch.setattr(sdk, "ClientSession", Session)
    client = BotTwitch("test-client", authenticate_app=False)
    asyncio.run(client.set_user_authentication("test-token", SCOPES, "test-refresh", validate=False))
    client.auto_refresh_auth = False
    start_chat()
    monkeypatch.setattr(state, "twitch", client, raising=False)
    monkeypatch.setattr(state, "bot_user_id", BOT, raising=False)
    return SimpleNamespace(stub=stub, handlers=handlers)


def call(helix, method, payload):
    assert method in helix.handlers, f"{method} 尚未註冊"
    return asyncio.run(helix.handlers[method](payload))


def test_清單帶出_Twitch_上已有的詞(helix, channel_id):
    helix.stub.terms.update({"t-1": "創作者後台加的", "t-2": "another"})

    result = call(helix, "blocked_terms.list", {"twitch_id": int(channel_id)})

    text = str(result)
    assert all(value in text for value in ("創作者後台加的", "another", "t-1", "t-2")), result


def test_新增把詞送到_Twitch_且回傳帶出新詞的_id(helix, channel_id):
    result = call(helix, "blocked_terms.add", {"twitch_id": int(channel_id), "text": "壞詞"})

    assert helix.stub.sent_texts("POST") == ["壞詞"]
    ((_, new_id),) = helix.stub.terms.items()
    assert "壞詞" in str(result) and new_id in str(result), result


def test_刪除以詞的_id_送到_Twitch(helix, channel_id):
    helix.stub.terms.update({"t-1": "留著", "t-2": "要刪"})

    call(helix, "blocked_terms.remove", {"twitch_id": int(channel_id), "term_id": "t-2"})

    assert helix.stub.removed_ids() == ["t-2"]
    assert helix.stub.terms == {"t-1": "留著"}


@pytest.mark.parametrize(
    ("method", "payload"),
    [
        ("blocked_terms.list", {}),
        ("blocked_terms.add", {"text": "壞詞"}),
        ("blocked_terms.remove", {"term_id": "t-1"}),
    ],
)
def test_bot_不是頻道_mod_時回_not_mod(helix, channel_id, method, payload):
    helix.stub.status = 403

    result = call(helix, method, {"twitch_id": int(channel_id), **payload})

    assert result == {"error": "not_mod"}


@pytest.mark.parametrize(
    ("method", "payload"),
    [
        ("blocked_terms.list", {}),
        ("blocked_terms.add", {"text": "壞詞"}),
        ("blocked_terms.remove", {"term_id": "t-1"}),
    ],
)
def test_其他_Twitch_失敗拋錯而不是回_not_mod(helix, channel_id, method, payload):
    helix.stub.status = 500

    assert method in helix.handlers
    with pytest.raises(Exception):  # noqa: B017 失敗型別由實作決定，只要求不回成功也不回 not_mod
        call(helix, method, {"twitch_id": int(channel_id), **payload})
