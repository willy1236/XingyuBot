"""starServer.dashboard.channel_health：頻道的權限問題與暫停的功能（mock Twitch Helix、bot RPC 與 token）。"""

import asyncio
from types import SimpleNamespace

import httpx
import pytest

from starlib import twitch_speech_check
from starlib.messaging.rpc import RpcHandlerError
from starlib.twitch_tokens import TokenInvalid
from starServer.dashboard import channel_activation, twitch_control
from starServer.dashboard import channel_health as health
from starServer.dashboard.channel_health import ChannelHealth
from starServer.dashboard.twitch_control import BotOffline, ChannelStatus, SubscriptionStatus
from starServer.twitch_bot import channels as bot_channels

TWITCH_ID = 777
BOT_ID = "42"
MOD_FEATURES = {
    "follow_response",
    "follow_forward",
    "subscribe_response",
    "subscribe_forward",
    "resubscribe_response",
    "resubscribe_forward",
    "gift_response",
    "gift_forward",
    "redemption_forward",
    "prediction_forward",
}
ALL_FEATURES = {f.code for f in health.FEATURES}
CHAT_FEATURES = {f.code for f in health.FEATURES if f.chat}


def run(coro):
    return asyncio.run(coro)


def status(joined=True, ok=(), failed=(), pending=False) -> ChannelStatus:
    return ChannelStatus(joined=joined, subscriptions=SubscriptionStatus(list(ok), list(failed), pending))


class FakeTwitch:
    """依路徑回應的 Twitch：預設一切正常（授權有效、bot 是 mod、沒被 ban 或封鎖、bot 在聊天室）。"""

    def __init__(self, monkeypatch, row_state="enabled"):
        self.requests: list[httpx.Request] = []
        self.scopes = list(channel_activation.ENABLE_SCOPES)
        self.validate = lambda: httpx.Response(200, json={"scopes": self.scopes})
        self.moderators = lambda: httpx.Response(200, json={"data": [{"user_id": BOT_ID}]})
        self.banned = lambda: httpx.Response(200, json={"data": []})
        self.blocks = lambda page: httpx.Response(200, json={"data": [], "pagination": {}})
        self.token: str | TokenInvalid = "token-1"
        self.bot_status: ChannelStatus | BotOffline | Exception = status()

        def respond(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            url = str(request.url).split("?")[0]
            if url == health.VALIDATE_URL:
                return self.validate()
            if url == health.MODERATORS_URL:
                return self.moderators()
            if url == health.BANNED_URL:
                return self.banned()
            if url == health.BLOCKS_URL:
                return self.blocks(request.url.params.get("after"))
            raise AssertionError(f"未預期的請求 {url}")

        real = httpx.AsyncClient
        monkeypatch.setattr(
            health.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(respond), **kw)
        )

        async def run_db(fn):
            return fn()

        async def broadcaster_token(twitch_id):
            return self.token

        async def channel_status(twitch_id):
            if isinstance(self.bot_status, Exception):
                raise self.bot_status
            return self.bot_status

        monkeypatch.setattr(health, "run_db", run_db)
        monkeypatch.setattr(health, "bot_user_id_blocking", lambda: BOT_ID)
        monkeypatch.setattr(health, "sqldb", SimpleNamespace(get=lambda model, key: SimpleNamespace(state=row_state)))
        monkeypatch.setattr(twitch_speech_check, "broadcaster_client_id_blocking", lambda: "client-1")
        monkeypatch.setattr(twitch_control, "broadcaster_token", broadcaster_token)
        monkeypatch.setattr(twitch_control, "channel_status", channel_status)

    def paths(self) -> list[str]:
        return [str(r.url).split("?")[0] for r in self.requests]


@pytest.fixture
def twitch(monkeypatch):
    return FakeTwitch(monkeypatch)


def test_功能對照表的事件名稱與_bot_的訂閱一致():
    # 事件新增、改名時這裡會紅，提醒同步 FEATURES 與 EVENTS_NEED_MOD
    assert health.EVENTS_NEED_MOD == set(bot_channels.MOD_EVENTS)
    known = set(bot_channels.BASE_EVENTS) | set(bot_channels.MOD_EVENTS)
    assert {e for f in health.FEATURES for e in f.events} <= known
    assert {f.code for f in health.FEATURES if f.needs_mod} == MOD_FEATURES


@pytest.mark.parametrize("row_state", ["inactive", "disabled"])
def test_未啟用與已停用不打任何_Twitch_或_bot(monkeypatch, row_state):
    fake = FakeTwitch(monkeypatch, row_state)
    assert run(health.channel_health(TWITCH_ID)) == ChannelHealth(row_state)
    assert fake.requests == []


def test_沒有頻道列視為未啟用(monkeypatch):
    fake = FakeTwitch(monkeypatch)
    monkeypatch.setattr(health, "sqldb", SimpleNamespace(get=lambda model, key: None))
    assert run(health.channel_health(TWITCH_ID)) == ChannelHealth("inactive")
    assert fake.requests == []


def test_一切正常是_enabled_沒有問題(twitch):
    assert run(health.channel_health(TWITCH_ID)) == ChannelHealth("enabled")


def test_請求帶對_token_與_bot(twitch):
    run(health.channel_health(TWITCH_ID))
    validate = next(r for r in twitch.requests if str(r.url).startswith(health.VALIDATE_URL))
    assert validate.headers["Authorization"] == "OAuth token-1"
    moderators = next(r for r in twitch.requests if str(r.url).startswith(health.MODERATORS_URL))
    assert moderators.headers["Authorization"] == "Bearer token-1" and moderators.headers["Client-Id"] == "client-1"
    assert moderators.url.params["broadcaster_id"] == str(TWITCH_ID) and moderators.url.params["user_id"] == BOT_ID


class TestNotMod:
    def test_拿掉_mod_只暫停需要_mod_的功能_自訂指令照常(self, twitch):
        twitch.moderators = lambda: httpx.Response(200, json={"data": []})
        result = run(health.channel_health(TWITCH_ID))
        assert result.state == "partial" and result.issues == ("not_mod",)
        assert set(result.paused_features) == MOD_FEATURES
        assert "speech" not in result.paused_features

    def test_查不到_mod_名單就略過(self, twitch):
        twitch.moderators = lambda: httpx.Response(500, json={})
        assert run(health.channel_health(TWITCH_ID)) == ChannelHealth("enabled")

    def test_已被退訂的_mod_事件不另外算訂閱失敗(self, twitch):
        twitch.moderators = lambda: httpx.Response(200, json={"data": []})
        twitch.bot_status = status(failed=["channel follow"])
        assert run(health.channel_health(TWITCH_ID)).issues == ("not_mod",)


class TestTokenInvalid:
    @pytest.mark.parametrize("reason", ["missing", "revoked"])
    def test_沒有或撤銷的授權暫停全部功能且不打_Twitch(self, twitch, reason):
        twitch.token = TokenInvalid(reason)
        result = run(health.channel_health(TWITCH_ID))
        assert result == ChannelHealth("partial", ("token_invalid",), tuple(f.code for f in health.FEATURES))
        assert set(result.paused_features) == ALL_FEATURES
        assert twitch.requests == []

    def test_Twitch_暫時無法回應時略過_不顯示授權失效(self, twitch):
        twitch.token = TokenInvalid("unavailable")
        assert run(health.channel_health(TWITCH_ID)) == ChannelHealth("enabled")
        assert twitch.requests == []

    def test_validate_回_401(self, twitch):
        twitch.validate = lambda: httpx.Response(401, json={"message": "invalid access token"})
        result = run(health.channel_health(TWITCH_ID))
        assert result.issues == ("token_invalid",) and set(result.paused_features) == ALL_FEATURES
        assert twitch.paths() == [health.VALIDATE_URL]

    def test_缺必要的_scope(self, twitch):
        twitch.scopes = twitch.scopes[:-1]
        assert run(health.channel_health(TWITCH_ID)).issues == ("token_invalid",)

    def test_validate_查不到就略過(self, twitch):
        twitch.validate = lambda: httpx.Response(503, json={})
        assert run(health.channel_health(TWITCH_ID)) == ChannelHealth("enabled")


class TestBotBanned:
    def test_被_ban(self, twitch):
        twitch.banned = lambda: httpx.Response(200, json={"data": [{"user_id": BOT_ID}]})
        result = run(health.channel_health(TWITCH_ID))
        assert result.issues == ("bot_banned",) and set(result.paused_features) == ALL_FEATURES

    def test_被封鎖_名單在第二頁(self, twitch):
        pages = {
            None: {"data": [{"user_id": "1"}], "pagination": {"cursor": "next"}},
            "next": {"data": [{"user_id": BOT_ID}], "pagination": {}},
        }
        twitch.blocks = lambda page: httpx.Response(200, json=pages[page])
        assert run(health.channel_health(TWITCH_ID)).issues == ("bot_banned",)

    def test_被_ban_時不再列進不了聊天室(self, twitch):
        twitch.banned = lambda: httpx.Response(200, json={"data": [{"user_id": BOT_ID}]})
        twitch.bot_status = status(joined=False)
        assert run(health.channel_health(TWITCH_ID)).issues == ("bot_banned",)

    def test_ban_查不到時仍用封鎖名單判定(self, twitch):
        twitch.banned = lambda: httpx.Response(500, json={})
        twitch.blocks = lambda page: httpx.Response(200, json={"data": [{"user_id": BOT_ID}], "pagination": {}})
        assert run(health.channel_health(TWITCH_ID)).issues == ("bot_banned",)

    def test_兩項都查不到就略過_不擋_mod_判定(self, twitch):
        twitch.banned = lambda: httpx.Response(500, json={})
        twitch.blocks = lambda page: httpx.Response(500, json={})
        twitch.moderators = lambda: httpx.Response(200, json={"data": []})
        assert run(health.channel_health(TWITCH_ID)).issues == ("not_mod",)

    def test_封鎖名單翻太多頁就當查不到(self, twitch):
        twitch.blocks = lambda page: httpx.Response(
            200, json={"data": [{"user_id": "1"}], "pagination": {"cursor": "more"}}
        )
        assert run(health.channel_health(TWITCH_ID)) == ChannelHealth("enabled")
        assert twitch.paths().count(health.BLOCKS_URL) == health.BLOCK_LIST_MAX_PAGES


class TestMalformedResponses:
    """Twitch 的某個回應格式不符時，只略過那一項，其他項目照常判定。"""

    BAD = [
        httpx.Response(200, text="<html>not json</html>"),
        httpx.Response(200, json=["list"]),
        httpx.Response(200, json={"no": "data"}),
        httpx.Response(200, json={"data": {"not": "a list"}}),
        httpx.Response(200, json={"data": ["not an object"], "pagination": "x"}),
    ]

    @pytest.mark.parametrize("bad", BAD)
    def test_封鎖名單格式不符_仍判出_not_mod(self, twitch, bad):
        twitch.blocks = lambda page: bad
        twitch.moderators = lambda: httpx.Response(200, json={"data": []})
        assert run(health.channel_health(TWITCH_ID)).issues == ("not_mod",)

    @pytest.mark.parametrize("bad", BAD)
    def test_mod_名單格式不符_仍判出_ban(self, twitch, bad):
        twitch.moderators = lambda: bad
        twitch.banned = lambda: httpx.Response(200, json={"data": [{"user_id": BOT_ID}]})
        assert run(health.channel_health(TWITCH_ID)).issues == ("bot_banned",)

    @pytest.mark.parametrize("bad", BAD)
    def test_ban_名單格式不符_仍判出_封鎖(self, twitch, bad):
        twitch.banned = lambda: bad
        twitch.blocks = lambda page: httpx.Response(200, json={"data": [{"user_id": BOT_ID}], "pagination": {}})
        assert run(health.channel_health(TWITCH_ID)).issues == ("bot_banned",)

    @pytest.mark.parametrize(
        "bad",
        [
            httpx.Response(200, text="not json"),
            httpx.Response(200, json=["list"]),
            httpx.Response(200, json={"scopes": "not a list"}),
            httpx.Response(200, json={}),
        ],
    )
    def test_validate_格式不符就略過_不判授權失效_其他項照常(self, twitch, bad):
        twitch.validate = lambda: bad
        twitch.moderators = lambda: httpx.Response(200, json={"data": []})
        assert run(health.channel_health(TWITCH_ID)).issues == ("not_mod",)

    def test_三項都格式不符就全部略過(self, twitch):
        bad = httpx.Response(200, text="oops")
        twitch.moderators = twitch.banned = lambda: bad
        twitch.blocks = lambda page: bad
        assert run(health.channel_health(TWITCH_ID)) == ChannelHealth("enabled")


class TestTimeout:
    def test_Twitch_判定逾時就略過_bot_狀態照常(self, twitch, monkeypatch):
        async def slow(twitch_id):
            await asyncio.sleep(5)
            return "token-1"

        monkeypatch.setattr(twitch_control, "broadcaster_token", slow)
        monkeypatch.setattr(health, "ACCESS_TIMEOUT", 0.05)
        twitch.bot_status = BotOffline()
        assert run(health.channel_health(TWITCH_ID)) == ChannelHealth("enabled", ("bot_offline",))

    def test_後續查詢逾時也略過(self, twitch, monkeypatch):
        async def slow_blocks(*args, **kwargs):
            await asyncio.sleep(5)

        monkeypatch.setattr(health, "_is_blocked", slow_blocks)
        monkeypatch.setattr(health, "ACCESS_TIMEOUT", 0.05)
        twitch.moderators = lambda: httpx.Response(200, json={"data": []})
        assert run(health.channel_health(TWITCH_ID)) == ChannelHealth("enabled")


class TestBotStatus:
    def test_離線時只列_bot_離線_不暫停任何功能_也不誤判權限(self, twitch):
        twitch.bot_status = BotOffline()
        assert run(health.channel_health(TWITCH_ID)) == ChannelHealth("enabled", ("bot_offline",))

    def test_離線與_not_mod_並存(self, twitch):
        twitch.bot_status = BotOffline()
        twitch.moderators = lambda: httpx.Response(200, json={"data": []})
        result = run(health.channel_health(TWITCH_ID))
        assert result.issues == ("not_mod", "bot_offline") and set(result.paused_features) == MOD_FEATURES

    def test_bot_內部出錯視為離線_不_raise(self, twitch):
        twitch.bot_status = RpcHandlerError("boom")
        assert run(health.channel_health(TWITCH_ID)).issues == ("bot_offline",)

    def test_不在聊天室暫停所有靠發言的功能_轉發照常(self, twitch):
        twitch.bot_status = status(joined=False)
        result = run(health.channel_health(TWITCH_ID))
        assert result.state == "partial" and result.issues == ("not_joined",)
        assert set(result.paused_features) == CHAT_FEATURES
        assert "follow_forward" not in result.paused_features

    def test_訂閱失敗只暫停依賴那個事件的功能(self, twitch):
        twitch.bot_status = status(failed=["channel subscription gift"])
        result = run(health.channel_health(TWITCH_ID))
        assert result.issues == ("subscription_failed",)
        assert set(result.paused_features) == {"gift_response", "gift_forward"}

    def test_沒有對應功能的事件訂閱失敗只列問題(self, twitch):
        twitch.bot_status = status(failed=["stream offline"])
        assert run(health.channel_health(TWITCH_ID)) == ChannelHealth("enabled", ("subscription_failed",))

    def test_訂閱還在進行中不算失敗(self, twitch):
        twitch.bot_status = status(failed=["channel follow"], pending=True)
        assert run(health.channel_health(TWITCH_ID)) == ChannelHealth("enabled")

    def test_token_失效時不再列訂閱失敗(self, twitch):
        twitch.token = TokenInvalid("revoked")
        twitch.bot_status = status(failed=["channel follow"])
        assert run(health.channel_health(TWITCH_ID)).issues == ("token_invalid",)

    def test_issues_依固定順序(self, twitch):
        twitch.moderators = lambda: httpx.Response(200, json={"data": []})
        twitch.bot_status = status(joined=False, failed=["stream online"])
        assert run(health.channel_health(TWITCH_ID)).issues == ("not_mod", "not_joined", "subscription_failed")


def test_to_json():
    assert ChannelHealth("partial", ("not_mod",), ("follow_forward",)).to_json() == {
        "state": "partial",
        "issues": ["not_mod"],
        "paused_features": ["follow_forward"],
    }
