"""twitch_bot.events 的事件回應：讀頻道設定、關閉、自訂文字與快取失效、追隨限流、讀取失敗的退路（真實 PostgreSQL，測完 rollback）。"""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from starlib import twitch_audit, twitch_event_responses
from starlib.messaging import cache_invalidation
from starlib.twitch_audit import AuditActor
from starServer.twitch_bot import events, speech, state

TWITCH_ID = 2000000081
ACTOR = AuditActor("twitch", "1", "streamer")


def run(coro):
    return asyncio.run(coro)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture(autouse=True)
def _env(monkeypatch, repo):
    for module in (events, twitch_event_responses, twitch_audit):
        monkeypatch.setattr(module, "sqldb", repo)
    monkeypatch.setattr(cache_invalidation, "invalidate", lambda *a, **k: None)
    monkeypatch.setattr(events, "_responses", {})
    monkeypatch.setattr(events, "_follow_last", {})
    monkeypatch.setattr(events, "_version", 0)
    monkeypatch.setattr(events, "get_bus", lambda: MagicMock())
    monkeypatch.setattr(speech, "_live", {})
    monkeypatch.setattr(state, "chat", MagicMock(send_message=AsyncMock()), raising=False)
    clock = Clock()
    monkeypatch.setattr(events, "_now", clock)
    return clock


@pytest.fixture
def clock(_env):
    return _env


def sent() -> list[str]:
    return [call.args[1] for call in state.chat.send_message.await_args_list]


def save(kind, enabled=True, template="自訂 {user}"):
    twitch_event_responses.save(TWITCH_ID, ACTOR, "dashboard", kind, enabled, template)


def follow_event(name="小明"):
    return SimpleNamespace(
        metadata=SimpleNamespace(message_timestamp=datetime.now(UTC)),
        event=SimpleNamespace(
            broadcaster_user_id=str(TWITCH_ID),
            broadcaster_user_login="host",
            broadcaster_user_name="主播",
            user_name=name,
            user_login=name,
        ),
    )


def enable(kind):
    """開啟事件並使用預設文字（沒有設定時預設是關閉）。"""
    save(kind, template=twitch_event_responses.DEFAULTS[kind])


def test_沒有設定時預設關閉_不發言_bus_事件照發(monkeypatch):
    bus = MagicMock()
    monkeypatch.setattr(events, "get_bus", lambda: bus)
    run(events.on_follow(follow_event()))
    assert sent() == []
    assert bus.publish.call_count == 1


def test_開啟後用預設文字():
    enable("follow")
    run(events.on_follow(follow_event()))
    assert sent() == ["感謝 小明 的追隨！"]
    assert state.chat.send_message.await_args.args[0] == "host"


def test_自訂文字與關閉會生效():
    save("follow", template="歡迎 {user} 來 {channel}")
    run(events.on_follow(follow_event()))
    assert sent() == ["歡迎 小明 來 主播"]


def test_關閉的事件不發言():
    save("follow", enabled=False, template="x")
    run(events.on_follow(follow_event()))
    assert sent() == []


def test_收到失效通知後改用新文字_沒收到前沿用快取(clock):
    enable("follow")
    run(events.on_follow(follow_event()))
    save("follow")
    clock.now += 60
    run(events.on_follow(follow_event()))
    assert sent() == ["感謝 小明 的追隨！", "感謝 小明 的追隨！"]  # 還沒收到通知，用快取
    run(events._on_invalidated(str(TWITCH_ID)))
    clock.now += 60
    run(events.on_follow(follow_event()))
    assert sent()[-1] == "自訂 小明"


def test_失效通知_key_為_None_清掉全部():
    events._responses[1] = {}
    events._responses[2] = {}
    run(events._on_invalidated(None))
    assert events._responses == {}


def test_讀取途中收到失效通知_舊值不存進快取(monkeypatch):
    def load_then_invalidate(twitch_id):
        asyncio.run_coroutine_threadsafe(events._on_invalidated(str(twitch_id)), loop).result()
        return {k: twitch_event_responses.default_response(k) for k in twitch_event_responses.KINDS}

    async def scenario():
        nonlocal loop
        loop = asyncio.get_running_loop()
        monkeypatch.setattr(events, "_load", load_then_invalidate)
        await events._response(TWITCH_ID, "follow")

    loop = None
    run(scenario())
    assert TWITCH_ID not in events._responses


def test_追隨回應每個頻道_10_秒內只回一則_不排隊(clock):
    enable("follow")
    run(events.on_follow(follow_event("甲")))
    clock.now += 9.9
    run(events.on_follow(follow_event("乙")))
    assert sent() == ["感謝 甲 的追隨！"]
    clock.now += 0.1
    run(events.on_follow(follow_event("丙")))
    assert sent() == ["感謝 甲 的追隨！", "感謝 丙 的追隨！"]


def test_追隨限流不影響其他頻道與_bus_事件(monkeypatch):
    bus = MagicMock()
    monkeypatch.setattr(events, "get_bus", lambda: bus)
    run(events.on_follow(follow_event("甲")))
    run(events.on_follow(follow_event("乙")))
    assert bus.publish.call_count == 2
    assert events._follow_response_due(TWITCH_ID + 1)


def test_讀取設定失敗時視為關閉_不發言_bus_事件照發(monkeypatch):
    def broken(twitch_id):
        raise RuntimeError("db down")

    bus = MagicMock()
    monkeypatch.setattr(events, "_load", broken)
    monkeypatch.setattr(events, "get_bus", lambda: bus)
    run(events.on_follow(follow_event()))
    assert sent() == []
    assert bus.publish.call_count == 1


def test_發言出錯不擋_bus_事件(monkeypatch):
    enable("follow")
    bus = MagicMock()
    monkeypatch.setattr(events, "get_bus", lambda: bus)
    monkeypatch.setattr(speech, "say", AsyncMock(side_effect=RuntimeError("boom")))
    run(events.on_follow(follow_event()))
    assert bus.publish.call_count == 1


def test_開台回應代入分類與標題(monkeypatch):
    async def fake_first(_):
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
            thumbnail_url="",
            tag_ids=[],
            tags=[],
            is_mature=False,
            profile_image_url="",
        )

    async def fake_hook(*_):
        return None

    monkeypatch.setattr(events, "first", fake_first)
    monkeypatch.setattr(events.timers, "on_stream_online", fake_hook)
    monkeypatch.setattr(state, "twitch", MagicMock(), raising=False)
    # 分類與標題由 speech 依模板查，這裡直接給
    monkeypatch.setattr(speech, "_channel_info", {TWITCH_ID: (1e18, speech.ChannelInfo("遊戲", "標題"))})
    monkeypatch.setattr(speech.time, "monotonic", lambda: 1e18)
    event = SimpleNamespace(
        metadata=SimpleNamespace(message_timestamp=datetime.now(UTC)),
        event=SimpleNamespace(
            broadcaster_user_id=str(TWITCH_ID),
            broadcaster_user_login="host",
            broadcaster_user_name="主播",
            started_at=datetime.now(UTC),
        ),
    )
    enable("stream_online")
    run(events.on_stream_online(event))
    assert sent() == ["主播 正在直播 遊戲！標題"]


def test_start_註冊失效_handler_並在_READY_重新綁_loop(monkeypatch):
    registered: list[tuple[str, object]] = []
    monkeypatch.setattr(
        cache_invalidation, "on_invalidate", lambda cache, handler, loop: registered.append((cache, loop))
    )
    loop = MagicMock()
    chat = MagicMock()
    monkeypatch.setattr(state, "loop", loop, raising=False)
    monkeypatch.setattr(state, "chat", chat, raising=False)
    events.start()
    assert registered == [("twitch_event_response", loop)]
    [(_event, ready)] = [c.args for c in chat.register_event.call_args_list]
    run(ready(None))
    assert registered[-1][0] == "twitch_event_response" and len(registered) == 2
