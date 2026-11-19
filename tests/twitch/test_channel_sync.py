"""twitch_bot.channels：web 即時同步（RPC）用的聊天室加入離開、背景訂閱、mod 判定與快取失效。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from starServer.twitch_bot import channels, state
from tests.twitch.test_channels import BASE, MOD, TWITCH_ID, eventsub, run, user  # noqa: F401  (fixture)

REAL_SLEEP = asyncio.sleep  # eventsub fixture 會把 asyncio.sleep 換成快速版


class FakeChat:
    """記錄 join_room、leave_room 的聊天室替身；in_rooms 是已在的房間。"""

    username = "star_bot"

    def __init__(self):
        self.in_rooms: set[str] = set()
        self.join_delay = 0.0
        self.join_failed: list[str] = []
        self.joined_calls: list[str] = []
        self.left_calls: list[str] = []

    def is_in_room(self, login):
        return login in self.in_rooms

    async def join_room(self, login):
        self.joined_calls.append(login)
        await REAL_SLEEP(self.join_delay)
        if not self.join_failed:
            self.in_rooms.add(login)
        return self.join_failed

    async def leave_room(self, login):
        self.left_calls.append(login)
        self.in_rooms.discard(login)


def _users(*users):
    async def get_users(user_ids):
        for found in users:
            if found.id in user_ids:
                yield found

    return get_users


@pytest.fixture
def bot(monkeypatch, eventsub):  # noqa: F811
    """sync 用的假環境：chat、Helix 使用者、DB 的頻道 row 與 bot 的 mod 狀態都可在測試裡調整。"""
    env = SimpleNamespace(
        chat=FakeChat(),
        row=SimpleNamespace(twitch_id=TWITCH_ID, state="enabled", login="host"),
        mod=False,
    )
    monkeypatch.setattr(state, "chat", env.chat, raising=False)
    monkeypatch.setattr(state, "twitch", SimpleNamespace(get_users=_users(user())), raising=False)
    monkeypatch.setattr(state, "join_channels", {})
    monkeypatch.setattr(channels, "rooms", {})
    monkeypatch.setattr(channels, "_pending", {})
    monkeypatch.setattr(channels, "_room_locks", {})
    monkeypatch.setattr(channels, "_subscription_locks", {})
    monkeypatch.setattr(channels, "_load_row", lambda twitch_id: env.row)

    async def bot_is_mod(twitch_id):
        return env.mod

    monkeypatch.setattr(channels, "bot_is_mod", bot_is_mod)
    return env


def pending() -> bool:
    return channels.channel_status(TWITCH_ID)["subscriptions"]["pending"]


async def sync_and_settle() -> bool:
    joined = await channels.sync_channel(TWITCH_ID)
    while pending():
        await asyncio.sleep(0)
    return joined


def test_sync_enabled_joins_room_and_subscribes_in_background(bot):
    async def scenario():
        joined = await channels.sync_channel(TWITCH_ID)
        # 聊天室處理完就回應，訂閱還在背景
        assert joined
        assert bot.chat.joined_calls == ["host"]
        assert pending()
        while pending():
            await asyncio.sleep(0)

    run(scenario())

    status = channels.channel_status(TWITCH_ID)
    assert status["joined"]
    assert set(status["subscriptions"]["ok"]) == BASE
    assert status["subscriptions"]["failed"] == []


def test_sync_disabled_leaves_room_and_cancels_subscriptions(bot, eventsub):
    async def scenario():
        await sync_and_settle()
        bot.row.state = "disabled"
        return await sync_and_settle()

    assert run(scenario()) is False

    assert bot.chat.left_calls == ["host"]
    assert TWITCH_ID not in channels.subscriptions
    assert eventsub.unsubscribe_topic.await_count == len(BASE)
    assert channels.channel_status(TWITCH_ID)["joined"] is False


def test_sync_is_idempotent_for_joined_channel(bot, eventsub):
    async def scenario():
        await sync_and_settle()
        await sync_and_settle()

    run(scenario())

    assert bot.chat.joined_calls == ["host"]
    assert len(eventsub.listened) == len(BASE)


def test_sync_follows_bot_mod_status(bot):
    async def scenario():
        await sync_and_settle()
        bot.mod = True
        await sync_and_settle()
        assert set(channels.subscriptions[TWITCH_ID].ids) == BASE | MOD
        bot.mod = False
        await sync_and_settle()

    run(scenario())

    assert set(channels.subscriptions[TWITCH_ID].ids) == BASE


def test_unknown_mod_status_keeps_existing_subscriptions(bot, eventsub):
    async def scenario():
        bot.mod = True
        await sync_and_settle()
        bot.mod = None
        await sync_and_settle()

    run(scenario())

    assert set(channels.subscriptions[TWITCH_ID].ids) == BASE | MOD
    eventsub.unsubscribe_topic.assert_not_awaited()


def test_sync_answers_within_deadline_when_join_is_slow(bot, monkeypatch):
    monkeypatch.setattr(channels, "ROOM_TIMEOUT", 0.05)
    bot.chat.join_delay = 5

    async def scenario():
        loop = asyncio.get_running_loop()
        started = loop.time()
        joined = await channels.sync_channel(TWITCH_ID)
        return joined, loop.time() - started

    joined, elapsed = run(scenario())

    assert joined is False
    assert elapsed < 1


def test_sync_reports_not_joined_when_twitch_refuses(bot):
    bot.chat.join_failed = ["host"]
    assert run(sync_and_settle()) is False


def test_sync_unknown_channel_is_not_joined(bot):
    bot.row = None
    assert run(sync_and_settle()) is False
    assert bot.chat.joined_calls == []
    assert bot.chat.left_calls == []


def test_leaving_a_room_the_bot_is_not_in_does_not_call_leave_room(bot):
    bot.row.state = "disabled"
    run(sync_and_settle())
    assert bot.chat.left_calls == []


def test_syncs_for_one_channel_run_one_after_another(bot):
    bot.chat.join_delay = 0.05

    async def scenario():
        await asyncio.gather(channels.sync_channel(TWITCH_ID), channels.sync_channel(TWITCH_ID))

    run(scenario())

    # 第二次呼叫等第一次結束才開始，所以看到已在聊天室而不重複加入
    assert bot.chat.joined_calls == ["host"]


def test_status_for_unknown_channel(bot):
    assert channels.channel_status(123) == {
        "joined": False,
        "subscriptions": {"ok": [], "failed": [], "pending": False},
    }


def test_on_ready_joins_current_rooms_not_startup_list(bot):
    channels.rooms[TWITCH_ID] = "host"
    chat = MagicMock(username="star_bot", join_room=AsyncMock())

    run(channels.on_ready(SimpleNamespace(chat=chat)))

    chat.join_room.assert_awaited_once_with(["host"])


def test_on_ready_without_rooms_does_not_join(bot):
    chat = MagicMock(username="star_bot", join_room=AsyncMock())
    run(channels.on_ready(SimpleNamespace(chat=chat)))
    chat.join_room.assert_not_awaited()


def test_channel_invalidation_reloads_that_channel(bot):
    bot.row.state = "disabled"
    run(channels._on_channel_invalidated(str(TWITCH_ID)))
    assert state.join_channels[TWITCH_ID].state == "disabled"

    bot.row = None
    run(channels._on_channel_invalidated(str(TWITCH_ID)))
    assert TWITCH_ID not in state.join_channels


def test_rpc_handlers_return_contract_shapes(bot):
    async def scenario():
        reply = await channels._rpc_sync({"twitch_id": TWITCH_ID})
        while pending():
            await asyncio.sleep(0)
        return reply, await channels._rpc_status({"twitch_id": TWITCH_ID})

    sync_reply, status_reply = run(scenario())

    assert sync_reply == {"accepted": True, "joined": True}
    assert status_reply["joined"] is True
    assert set(status_reply["subscriptions"]) == {"ok", "failed", "pending"}


# ---- bot 是不是 mod：實況主 token + Helix ----


class FakeHelix:
    def __init__(self):
        self.status = 200
        self.data: list[dict] = [{"user_id": "42"}]
        self.error: Exception | None = None
        self.requests: list[dict] = []

    def client_class(self):
        outer = self

        class Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return None

            async def get(self, url, params, headers):
                outer.requests.append({"url": url, "params": params, "headers": headers})
                if outer.error:
                    raise outer.error
                return SimpleNamespace(status_code=outer.status, json=lambda: {"data": outer.data}, text="")

        return Client


@pytest.fixture
def helix(monkeypatch):
    monkeypatch.setattr(state, "bot_user_id", "42", raising=False)
    monkeypatch.setattr(channels, "_client_id", "client-3")

    async def token(twitch_id):
        return "broadcaster-token"

    monkeypatch.setattr(channels.twitch_tokens, "broadcaster_token", token)
    fake = FakeHelix()
    client_class = fake.client_class()
    monkeypatch.setattr(channels.httpx, "AsyncClient", lambda **kwargs: client_class())
    return fake


def test_bot_is_mod_uses_broadcaster_token_and_filters_by_bot(helix):
    assert run(channels.bot_is_mod(TWITCH_ID)) is True

    request = helix.requests[0]
    assert request["params"] == {"broadcaster_id": str(TWITCH_ID), "user_id": "42"}
    assert request["headers"] == {"Authorization": "Bearer broadcaster-token", "Client-Id": "client-3"}


def test_bot_is_not_mod_when_not_listed(helix):
    helix.data = []
    assert run(channels.bot_is_mod(TWITCH_ID)) is False


@pytest.mark.parametrize("status", [401, 403])
def test_bot_is_not_mod_when_token_rejected_or_missing_scope(helix, status):
    helix.status = status
    assert run(channels.bot_is_mod(TWITCH_ID)) is False


@pytest.mark.parametrize(("reason", "expected"), [("missing", False), ("revoked", False), ("unavailable", None)])
def test_unusable_broadcaster_token(helix, monkeypatch, reason, expected):
    async def token(twitch_id):
        return channels.TokenInvalid(reason)

    monkeypatch.setattr(channels.twitch_tokens, "broadcaster_token", token)

    assert run(channels.bot_is_mod(TWITCH_ID)) is expected
    assert helix.requests == []


def test_helix_server_error_is_unknown(helix):
    helix.status = 503
    assert run(channels.bot_is_mod(TWITCH_ID)) is None


def test_helix_unreachable_is_unknown(helix):
    helix.error = channels.httpx.ConnectError("down")
    assert run(channels.bot_is_mod(TWITCH_ID)) is None


# ---- chat 重啟：Chat 換了新的 loop ----


@pytest.fixture
def registrations(monkeypatch):
    handle, on_invalidate = MagicMock(), MagicMock()
    monkeypatch.setattr(channels.rpc, "handle", handle)
    monkeypatch.setattr(channels.cache_invalidation, "on_invalidate", on_invalidate)
    monkeypatch.setattr(channels, "_registered", False)
    return handle, on_invalidate


def ready(chat=None):
    return SimpleNamespace(chat=chat or MagicMock(username="star_bot", join_room=AsyncMock()))


def test_on_ready_does_not_register_before_register_is_called(bot, registrations):
    run(channels.on_ready(ready()))
    registrations[0].assert_not_called()


def test_restart_rebinds_handlers_and_drops_state_of_the_old_loop(bot, registrations, monkeypatch):
    handle, on_invalidate = registrations
    loops = []

    async def first_ready():
        loops.append(asyncio.get_running_loop())
        await channels.on_ready(ready())
        channels.register()
        channels._room_locks[TWITCH_ID] = asyncio.Lock()
        channels._pending[TWITCH_ID] = 1

    async def second_ready():
        loops.append(asyncio.get_running_loop())
        await channels.on_ready(ready())

    run(first_ready())
    assert handle.call_args_list[0].args[2] is loops[0]

    run(second_ready())

    assert state.loop is loops[1]
    assert {call.args[0]: call.args[2] for call in handle.call_args_list[2:]} == {
        "channel.sync": loops[1],
        "channel.status": loops[1],
    }
    assert on_invalidate.call_args_list[-1].args[2] is loops[1]
    assert channels._room_locks == {}
    assert channels._pending == {}


def test_ready_on_the_same_loop_keeps_registrations(bot, registrations):
    async def scenario():
        await channels.on_ready(ready())
        channels.register()
        channels._pending[TWITCH_ID] = 1
        await channels.on_ready(ready())

    run(scenario())

    assert registrations[0].call_count == 2
    assert channels._pending == {TWITCH_ID: 1}
