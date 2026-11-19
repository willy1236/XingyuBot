"""events.py、commands.py 呼叫 timers 的時機：W-06 只改 timers.py，呼叫點在這裡固定下來。"""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from starServer.twitch_bot import commands, events, state

TWITCH_ID = 900000000000000001


def run(coro):
    return asyncio.run(coro)


async def agen(*items):
    for item in items:
        yield item


def stream_event():
    return SimpleNamespace(
        metadata=SimpleNamespace(message_timestamp=datetime.now(UTC)),
        event=SimpleNamespace(
            broadcaster_user_id=str(TWITCH_ID),
            broadcaster_user_login="host",
            broadcaster_user_name="主播",
            started_at=datetime.now(UTC),
        ),
    )


@pytest.fixture
def calls(monkeypatch):
    recorded: list[tuple] = []
    for name in ("on_stream_online", "on_stream_offline", "on_chat_message"):

        async def hook(*args, _name=name):
            recorded.append((_name, *args))

        monkeypatch.setattr(events.timers, name, hook)
    monkeypatch.setattr(events, "get_bus", lambda: MagicMock())
    monkeypatch.setattr(state, "join_channels", {})
    monkeypatch.setattr(state, "chat", MagicMock(username="Star_Bot", send_message=AsyncMock()), raising=False)
    return recorded


def live_stream():
    return SimpleNamespace(
        id="1",
        user_login="host",
        game_id="g",
        game_name="遊戲",
        type="live",
        title="標題",
        viewer_count=1,
        started_at=datetime.now(UTC),
        language="zh",
        thumbnail_url="x",
        tag_ids=[],
        tags=[],
        is_mature=False,
    )


def test_online_calls_timers_after_live_is_confirmed(calls, monkeypatch):
    monkeypatch.setattr(
        state,
        "twitch",
        MagicMock(
            get_streams=lambda user_id: agen(live_stream()),
            get_users=lambda user_ids: agen(SimpleNamespace(profile_image_url=None)),
        ),
        raising=False,
    )
    run(events.on_stream_online(stream_event()))
    assert calls == [("on_stream_online", TWITCH_ID)]


def test_online_without_live_stream_does_not_call_timers(calls, monkeypatch):
    monkeypatch.setattr(state, "twitch", MagicMock(get_streams=lambda user_id: agen()), raising=False)
    monkeypatch.setattr(events.asyncio, "sleep", AsyncMock())
    run(events.on_stream_online(stream_event()))
    assert calls == []


def test_offline_calls_timers(calls):
    run(events.on_stream_offline(stream_event()))
    assert calls == [("on_stream_offline", TWITCH_ID)]


@pytest.mark.parametrize(("author", "is_bot"), [("star_bot", True), ("Viewer", False)])
def test_chat_message_tells_timers_whether_author_is_bot(calls, monkeypatch, author, is_bot):
    monkeypatch.setattr(commands, "respond_to_chat_command", AsyncMock())
    msg = SimpleNamespace(
        room=SimpleNamespace(room_id=str(TWITCH_ID), name="host"), user=SimpleNamespace(name=author), text="hi"
    )
    run(commands.on_message(msg))
    assert calls == [("on_chat_message", TWITCH_ID, is_bot)]
