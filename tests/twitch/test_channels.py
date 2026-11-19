"""twitch_bot.channels：EventSub 訂閱的補訂、退訂與 id 記錄。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from twitchAPI.type import EventSubSubscriptionError

from starServer.twitch_bot import channels, state

TWITCH_ID = 900000000000000001
BASE = set(channels.BASE_EVENTS)
MOD = set(channels.MOD_EVENTS)


class FakeEventSub:
    """每個 listen_* 都回新的 subscription id；fail 內的方法名稱會拋 EventSubSubscriptionError。"""

    def __init__(self, fail: frozenset[str] = frozenset()):
        self.fail = fail
        self.count = 0
        self.listened: list[str] = []
        self.unsubscribe_topic = AsyncMock(return_value=True)

    def __getattr__(self, name: str):
        if not name.startswith("listen_"):
            raise AttributeError(name)

        async def listen(*args, **kwargs) -> str:
            self.listened.append(name)
            if name in self.fail:
                raise EventSubSubscriptionError("boom")
            self.count += 1
            return f"sub-{self.count}"

        return listen


@pytest.fixture
def eventsub(monkeypatch):
    fake = FakeEventSub()
    monkeypatch.setattr(state, "eventsub", fake, raising=False)
    monkeypatch.setattr(state, "bot_user_id", "42", raising=False)
    monkeypatch.setattr(channels, "subscriptions", {})
    real_sleep = asyncio.sleep

    async def fast_sleep(delay, *args):
        # 訂閱之間的 1 秒間隔不用等；仍要讓出 loop，背景任務才跑得動
        await real_sleep(0)

    monkeypatch.setattr(channels.asyncio, "sleep", fast_sleep)
    return fake


def user() -> SimpleNamespace:
    return SimpleNamespace(id=str(TWITCH_ID), login="host")


def run(coro):
    return asyncio.run(coro)


def test_non_mod_subscribes_only_base_events(eventsub):
    run(channels.subscribe_channel(user(), is_mod=False))

    assert set(channels.subscriptions[TWITCH_ID].ids) == BASE
    assert len(eventsub.listened) == len(BASE)


def test_mod_subscribes_base_and_mod_events(eventsub):
    run(channels.subscribe_channel(user(), is_mod=True))

    assert set(channels.subscriptions[TWITCH_ID].ids) == BASE | MOD


def test_repeated_sync_does_not_resubscribe(eventsub):
    run(channels.subscribe_channel(user(), is_mod=True))
    first = len(eventsub.listened)
    run(channels.subscribe_channel(user(), is_mod=True))

    assert len(eventsub.listened) == first
    eventsub.unsubscribe_topic.assert_not_awaited()


def test_gaining_mod_adds_only_missing_events(eventsub):
    run(channels.subscribe_channel(user(), is_mod=False))
    run(channels.subscribe_channel(user(), is_mod=True))

    assert set(channels.subscriptions[TWITCH_ID].ids) == BASE | MOD
    assert len(eventsub.listened) == len(BASE | MOD)


def test_losing_mod_unsubscribes_mod_events_by_id(eventsub):
    run(channels.subscribe_channel(user(), is_mod=True))
    mod_ids = {channels.subscriptions[TWITCH_ID].ids[name] for name in MOD}
    run(channels.subscribe_channel(user(), is_mod=False))

    assert set(channels.subscriptions[TWITCH_ID].ids) == BASE
    assert {call.args[0] for call in eventsub.unsubscribe_topic.await_args_list} == mod_ids


def test_failed_subscription_is_recorded_and_retried(eventsub):
    eventsub.fail = frozenset({"listen_stream_online"})
    run(channels.subscribe_channel(user(), is_mod=False))

    subs = channels.subscriptions[TWITCH_ID]
    assert subs.failed == ["stream online"]
    assert set(subs.ids) == BASE - {"stream online"}

    eventsub.fail = frozenset()
    run(channels.subscribe_channel(user(), is_mod=False))
    assert subs.failed == []
    assert set(subs.ids) == BASE


def test_unsubscribe_channel_cancels_every_subscription(eventsub):
    run(channels.subscribe_channel(user(), is_mod=True))
    ids = set(channels.subscriptions[TWITCH_ID].ids.values())

    run(channels.unsubscribe_channel(TWITCH_ID))

    assert TWITCH_ID not in channels.subscriptions
    assert {call.args[0] for call in eventsub.unsubscribe_topic.await_args_list} == ids
