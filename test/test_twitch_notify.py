"""Twitch 追隨通知：Discord 端的目的頻道解析與 handler，以及追隨事件經 Redis 的來回。"""

from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlmodel import Session, update

from starDiscord.cmds import twitch_notify
from starDiscord.cmds.twitch_notify import ChannelMissing, NotConfigured, TwitchNotify, resolve_action_channel
from starlib import sqldb
from starlib.database import TwitchBotJoinChannel
from starlib.database.postgresql.client import SQLRepository
from starlib.messaging import Delivery, MessageBus
from starlib.messaging.events.twitch_follow import TwitchFollowEvent

TWITCH_ID = "900000000000000002"


def make_event(**overrides) -> TwitchFollowEvent:
    fields = dict(
        occurred_at=datetime.now(UTC),
        broadcaster_id=TWITCH_ID,
        broadcaster_name="主播",
        follower_name="追隨者",
        follower_login="follower_login",
    )
    return TwitchFollowEvent(**{**fields, **overrides})


@pytest.fixture
def join_config(monkeypatch):
    """替換 sqldb.get_twitch_join_channel；回傳可設定的 holder。"""
    holder = SimpleNamespace(value=None)
    monkeypatch.setattr(twitch_notify.sclient.sqldb, "get_twitch_join_channel", lambda twitch_id: holder.value)
    return holder


@pytest.fixture
def sentry_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(twitch_notify, "capture_message_safe", lambda *a, **k: calls.append((a, k)))
    return calls


def test_resolve_not_configured_when_no_row(join_config):
    assert resolve_action_channel(MagicMock(), TWITCH_ID) == NotConfigured()


def test_resolve_not_configured_when_channel_id_empty(join_config):
    join_config.value = SimpleNamespace(action_channel_id=None)
    assert resolve_action_channel(MagicMock(), TWITCH_ID) == NotConfigured()


def test_resolve_channel_missing_logs_and_reports(join_config, sentry_calls):
    join_config.value = SimpleNamespace(action_channel_id=123)
    bot = MagicMock()
    bot.get_channel.return_value = None
    assert resolve_action_channel(bot, TWITCH_ID) == ChannelMissing()
    assert len(sentry_calls) == 1


def test_resolve_returns_channel(join_config, sentry_calls):
    join_config.value = SimpleNamespace(action_channel_id=123)
    bot = MagicMock()
    channel = object()
    bot.get_channel.return_value = channel
    assert resolve_action_channel(bot, TWITCH_ID) is channel
    bot.get_channel.assert_called_once_with(123)
    assert sentry_calls == []


def make_cog(monkeypatch) -> TwitchNotify:
    subscribed = MagicMock()
    monkeypatch.setattr(twitch_notify, "get_bus", lambda: subscribed)
    return TwitchNotify(MagicMock())


def test_follow_sends_same_text_as_before(monkeypatch, join_config):
    cog = make_cog(monkeypatch)
    channel = MagicMock()
    channel.send = AsyncMock()
    monkeypatch.setattr(twitch_notify, "resolve_action_channel", lambda bot, twitch_id: channel)
    asyncio.run(cog.on_follow(make_event(), Delivery(redelivered=False)))
    channel.send.assert_awaited_once_with("追隨者(follower_login) 正在追隨 主播!")


@pytest.mark.parametrize("result", [NotConfigured(), ChannelMissing()])
def test_follow_sends_nothing_without_channel(monkeypatch, result):
    cog = make_cog(monkeypatch)
    monkeypatch.setattr(twitch_notify, "resolve_action_channel", lambda bot, twitch_id: result)
    asyncio.run(cog.on_follow(make_event(), Delivery(redelivered=False)))  # 不拋例外即可


def test_cog_subscribes_follow_event_on_bot_loop(monkeypatch):
    bus = MagicMock()
    monkeypatch.setattr(twitch_notify, "get_bus", lambda: bus)
    bot = MagicMock()
    TwitchNotify(bot)
    subscribed = {call.args[0]: call for call in bus.subscribe.call_args_list}
    assert TwitchFollowEvent in subscribed
    assert all(call.kwargs["loop"] is bot.loop for call in subscribed.values())


def test_cog_unload_unsubscribes_its_handler(monkeypatch):
    bus = MagicMock()
    monkeypatch.setattr(twitch_notify, "get_bus", lambda: bus)
    cog = TwitchNotify(MagicMock())
    cog.cog_unload()
    bus.unsubscribe.assert_any_call(TwitchFollowEvent, cog.on_follow)


@pytest.mark.integration
def test_get_twitch_join_channel_reads_latest_config():
    """同一個 session 內設定被改過，下一次查詢要拿到新值（不被 identity map 擋住）。"""
    connection = sqldb.engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    repo = SQLRepository(sqldb.engine, session)
    try:
        twitch_id = 2000000001
        session.add(TwitchBotJoinChannel(twitch_id=twitch_id, action_channel_id=111))
        session.flush()
        assert repo.get_twitch_join_channel(str(twitch_id)).action_channel_id == 111
        session.exec(update(TwitchBotJoinChannel).where(TwitchBotJoinChannel.twitch_id == twitch_id).values(action_channel_id=222))
        assert repo.get_twitch_join_channel(twitch_id).action_channel_id == 222
        assert repo.get_twitch_join_channel(twitch_id + 1) is None
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.mark.integration
def test_follow_event_travels_between_two_buses():
    """Twitch 端（發送）→ Redis → Discord 端（消費）：欄位原樣到達，handler 在指定的 loop 上執行。"""
    prefix = f"test-twitch-notify-{uuid4().hex}"
    sender = MessageBus(prefix)
    receiver = MessageBus(prefix)
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    received: list[tuple[TwitchFollowEvent, Delivery, asyncio.AbstractEventLoop]] = []
    done = threading.Event()

    async def handler(event: TwitchFollowEvent, delivery: Delivery) -> None:
        received.append((event, delivery, asyncio.get_running_loop()))
        done.set()

    try:
        receiver.subscribe(TwitchFollowEvent, handler, loop)
        receiver.start("discord")
        event = make_event()
        sender.publish(event)
        assert done.wait(10)
        got, delivery, handler_loop = received[0]
        assert got == event
        assert delivery.redelivered is False
        assert handler_loop is loop
    finally:
        sender.close()
        receiver.close()
        loop.call_soon_threadsafe(loop.stop)
        thread.join(5)


def test_discord_close_closes_bus_before_super_close(monkeypatch):
    """關機時 bus 要在 loop 還活著時先關，否則關機時間窗內讀到的事件會被誤 ack。"""
    import discord

    from starDiscord import bot as bot_module

    order: list[str] = []
    bus = MagicMock()
    close_threads: list[int] = []

    def fake_bus_close():
        order.append("bus.close")
        close_threads.append(threading.get_ident())

    bus.close.side_effect = fake_bus_close
    monkeypatch.setattr(bot_module, "get_bus", lambda: bus)

    async def fake_super_close(self):
        order.append("super.close")

    monkeypatch.setattr(discord.Bot, "close", fake_super_close)

    async def run():
        fake = bot_module.DiscordBot.__new__(bot_module.DiscordBot)
        fake.scheduler = SimpleNamespace(running=False)
        fake.loop = asyncio.get_running_loop()
        await fake.close()

    asyncio.run(run())
    assert order == ["bus.close", "super.close"]
    # 不能在 loop thread 上關：handler 需要 loop 才能結束，會被自己卡住
    assert close_threads[0] != threading.get_ident()


def test_discord_close_still_closes_bot_when_bus_close_fails(monkeypatch):
    import discord

    from starDiscord import bot as bot_module

    bus = MagicMock()
    bus.close.side_effect = RuntimeError("boom")
    monkeypatch.setattr(bot_module, "get_bus", lambda: bus)
    closed = []

    async def fake_super_close(self):
        closed.append(True)

    monkeypatch.setattr(discord.Bot, "close", fake_super_close)

    async def run():
        fake = bot_module.DiscordBot.__new__(bot_module.DiscordBot)
        fake.scheduler = SimpleNamespace(running=False)
        fake.loop = asyncio.get_running_loop()
        with pytest.raises(RuntimeError):
            await fake.close()

    asyncio.run(run())
    assert closed == [True]
