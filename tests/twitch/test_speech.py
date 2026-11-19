"""twitch_bot.speech：變數代入、發言前的 AutoMod 檢查與擋下紀錄。"""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from starServer.twitch_bot import events, speech, state
from starServer.twitch_bot.speech import SpeechContext, StreamInfo

TWITCH_ID = 2000000041
NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)


def run(coro):
    return asyncio.run(coro)


def ctx(**kw) -> SpeechContext:
    return SpeechContext(twitch_id=TWITCH_ID, channel="頻道名", now=NOW, **kw)


@pytest.fixture(autouse=True)
def _reset(monkeypatch, repo):
    # 擋下紀錄寫進綁在外層交易的 repo，測完 rollback
    monkeypatch.setattr(speech, "sqldb", repo)
    monkeypatch.setattr(speech, "_live", {})
    monkeypatch.setattr(speech, "_channel_info", {})
    monkeypatch.setattr(speech, "_check_cache", {})
    monkeypatch.setattr(state, "chat", MagicMock(send_message=AsyncMock()), raising=False)
    monkeypatch.setattr(state, "twitch", MagicMock(), raising=False)


# ── render ──


def test_模板代入變數():
    text = speech.render("感謝 {user}，已經 {count} 次，來自 {channel}", ctx(user="小明", count=3))
    assert text == "感謝 小明，已經 3 次，來自 頻道名"


def test_不認得的變數與沒提供的變數原樣保留():
    text = speech.render("{nope} {args} {user} {count}", ctx())
    assert text == "{nope} {args} {user} {count}"


def test_touser_沒有參數用觸發者_有參數用第一個字():
    assert speech.render("{touser}", ctx(user="小明", args="")) == "小明"
    assert speech.render("{touser}", ctx(user="小明")) == "小明"
    assert speech.render("{touser}", ctx(user="小明", args="@阿華 你好")) == "阿華"
    assert speech.render("{args}", ctx(user="小明", args="@阿華 你好")) == "@阿華 你好"


def test_沒開台時_uptime_是未開台():
    assert speech.render("{uptime}", ctx()) == "未開台"


@pytest.mark.parametrize(
    ("elapsed", "expected"),
    [
        (timedelta(seconds=30), "不到 1 分鐘"),
        (timedelta(minutes=5), "5 分"),
        (timedelta(hours=2, minutes=3), "2 小時 3 分"),
    ],
)
def test_uptime_格式(elapsed, expected):
    stream = StreamInfo(NOW - elapsed, "g", "t")
    assert speech.render("{uptime}", ctx(stream=stream)) == expected


def test_事件變數與分類標題():
    context = ctx(event={"months": "6", "viewers": "12"}, channel_info=speech.ChannelInfo("遊戲", "標題"))
    assert speech.render("{months} {viewers} {amount} {game} {title}", context) == "6 12 {amount} 遊戲 標題"
    assert speech.render("{game}", ctx()) == "未知"


def test_觀眾輸入的大括號不會被再展開():
    assert speech.render("{args}", ctx(user="小明", args="{user}")) == "{user}"


# ── prepare ──


def test_沒用到開台與分類變數就不查_Helix():
    run(speech.prepare("hi {user}", ctx(user="a")))
    state.twitch.get_streams.assert_not_called()
    state.twitch.get_channel_information.assert_not_called()


def test_uptime_惰性查一次開台狀態並記住():
    calls = 0

    async def streams(user_id):
        nonlocal calls
        calls += 1
        yield SimpleNamespace(started_at=NOW - timedelta(minutes=10), game_name="g", title="t")

    state.twitch.get_streams = streams
    first = run(speech.prepare("{uptime}", ctx()))
    assert speech.render("{uptime}", first) == "10 分"
    run(speech.prepare("{uptime}", ctx()))
    assert calls == 1


def test_已由事件得知的開台狀態不再查():
    speech.set_offline(TWITCH_ID)
    result = run(speech.prepare("{uptime}", ctx()))
    state.twitch.get_streams.assert_not_called()
    assert speech.render("{uptime}", result) == "未開台"
    speech.set_live(TWITCH_ID, StreamInfo(NOW - timedelta(hours=1), "g", "t"))
    assert speech.render("{uptime}", run(speech.prepare("{uptime}", ctx()))) == "1 小時 0 分"


def test_分類與標題快取_60_秒(monkeypatch):
    state.twitch.get_channel_information = AsyncMock(return_value=[SimpleNamespace(game_name="g", title="t")])
    clock = [1000.0]
    monkeypatch.setattr(speech.time, "monotonic", lambda: clock[0])
    run(speech.prepare("{game}", ctx()))
    clock[0] += 59
    run(speech.prepare("{title}", ctx()))
    assert state.twitch.get_channel_information.await_count == 1
    clock[0] += 2
    run(speech.prepare("{game}", ctx()))
    assert state.twitch.get_channel_information.await_count == 2


# ── say ──


@pytest.fixture
def check(monkeypatch):
    mock = AsyncMock(return_value="ok")
    monkeypatch.setattr(speech, "check_text", mock)
    return mock


def say(template, context, **kw):
    kw.setdefault("source_kind", "command")
    kw.setdefault("source_key", "hi")
    return run(speech.say("host", TWITCH_ID, template, context, **kw))


def test_不含觀眾輸入的訊息不檢查_直接送出(check):
    assert say("感謝 {user} {count}", ctx(user="小明", count=2)) is True
    check.assert_not_awaited()
    state.chat.send_message.assert_awaited_once_with("host", "感謝 小明 2")


def test_有_reply_to_時用回覆(check):
    message = MagicMock(reply=AsyncMock())
    assert say("hi {user}", ctx(user="a"), reply_to=message) is True
    message.reply.assert_awaited_once_with("hi a")
    state.chat.send_message.assert_not_awaited()


def test_含_args_通過檢查就送出(check):
    assert say("你說 {args}", ctx(user="a", args="哈囉")) is True
    check.assert_awaited_once_with(TWITCH_ID, "你說 哈囉")
    state.chat.send_message.assert_awaited_once()


def test_含_args_被擋下時不送出並寫擋下紀錄(check):
    check.return_value = "blocked"
    assert say("你說 {args}", ctx(user="a", args="壞話"), source_key="hello") is False
    state.chat.send_message.assert_not_awaited()
    [row] = speech.sqldb.list_twitch_automod_blocks(TWITCH_ID)
    assert (row.source_kind, row.source_key, row.text, row.reason) == ("command", "hello", "你說 壞話", "automod")


def test_含_touser_檢查失敗時不送出並標原因(check):
    check.return_value = "unavailable"
    assert say("hi {touser}", ctx(user="a")) is False
    state.chat.send_message.assert_not_awaited()
    [row] = speech.sqldb.list_twitch_automod_blocks(TWITCH_ID)
    assert row.reason == "check_failed"


def test_同頻道同文字的檢查結果快取_10_分鐘(check, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(speech.time, "monotonic", lambda: clock[0])
    say("{args}", ctx(args="a"))
    say("{args}", ctx(args="a"))
    assert check.await_count == 1
    say("{args}", ctx(args="b"))
    assert check.await_count == 2
    clock[0] += 601
    say("{args}", ctx(args="a"))
    assert check.await_count == 3


def test_檢查失敗的結果不快取(check):
    check.return_value = "unavailable"
    say("{args}", ctx(args="a"))
    check.return_value = "ok"
    assert say("{args}", ctx(args="a")) is True
    assert check.await_count == 2


def test_超過_500_字會截斷(check):
    say("{user}", ctx(user="x" * 600))
    assert len(state.chat.send_message.await_args.args[1]) == 500


def test_say_不_raise(check):
    state.chat.send_message = AsyncMock(side_effect=RuntimeError("boom"))
    assert say("hi", ctx()) is False
    check.side_effect = RuntimeError("boom")
    assert say("{args}", ctx(args="a")) is False


# ── events 維護開台資訊 ──


def test_開台與下播事件維護開台資訊(monkeypatch):
    monkeypatch.setattr(events, "get_bus", lambda: MagicMock())
    monkeypatch.setattr(events.timers, "on_stream_online", AsyncMock())
    monkeypatch.setattr(events.timers, "on_stream_offline", AsyncMock())
    monkeypatch.setattr(state, "join_channels", {})
    started = NOW - timedelta(minutes=1)

    async def streams(user_id):
        yield SimpleNamespace(
            id="1",
            user_login="host",
            game_id="1",
            game_name="g",
            type="live",
            title="t",
            viewer_count=1,
            started_at=started,
            language="zh",
            thumbnail_url="x",
            tag_ids=[],
            tags=[],
            is_mature=False,
        )

    async def users(user_ids):
        yield SimpleNamespace(profile_image_url="p")

    state.twitch.get_streams = streams
    state.twitch.get_users = users
    event = SimpleNamespace(
        metadata=SimpleNamespace(message_timestamp=NOW),
        event=SimpleNamespace(
            broadcaster_user_id=str(TWITCH_ID), broadcaster_user_login="host", broadcaster_user_name="主播"
        ),
    )
    run(events.on_stream_online(event))
    assert speech.current_stream(TWITCH_ID) == StreamInfo(started, "g", "t")
    run(events.on_stream_offline(event))
    assert speech.current_stream(TWITCH_ID) is None
    assert speech._live == {TWITCH_ID: None}
