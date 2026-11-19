"""twitch_bot.timers：計時訊息的間隔、開台與下播、最少聊天量、設定重讀與 Chat 重啟（時間用假時鐘，發言與 Helix 用 mock）。"""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from starlib.database import TwitchTimer
from starServer.twitch_bot import channels, speech, timers

TWITCH_ID = 2000000091
OTHER_ID = 2000000092
LOGIN = "host"


def run(coro):
    return asyncio.run(coro)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def config(timer_id=1, message="追隨喔", interval=10, lines=0, enabled=True):
    return timers.TimerConfig(timer_id, message, interval, lines, enabled)


@pytest.fixture(autouse=True)
def _env(monkeypatch, repo):
    monkeypatch.setattr(timers, "sqldb", repo)
    monkeypatch.setattr(timers, "_configs", {})
    monkeypatch.setattr(timers, "_runtime", {})
    monkeypatch.setattr(timers, "_online", {})
    clock = Clock()
    monkeypatch.setattr(timers, "_now", clock)
    monkeypatch.setattr(channels, "rooms", {TWITCH_ID: LOGIN})
    monkeypatch.setattr(speech, "say", AsyncMock(return_value=True))
    monkeypatch.setattr(speech, "prepare", AsyncMock())
    return clock


@pytest.fixture
def clock(_env):
    return _env


def setup_channel(*configs, online=True, twitch_id=TWITCH_ID):
    """直接放入設定；online 為真時用 on_stream_online 開台（從目前時間起算）。"""
    timers._apply(twitch_id, list(configs))
    if online:
        run(timers.on_stream_online(twitch_id))


async def tick_and_settle():
    await timers.tick()
    await asyncio.sleep(0)


# ── 間隔與開台 ──


def test_開台後第一則等滿一個間隔才發(clock):
    setup_channel(config(interval=10))
    clock.now += 599
    run(timers.tick())
    speech.say.assert_not_awaited()
    clock.now += 1
    run(timers.tick())
    assert speech.say.await_count == 1


def test_發送的參數是計時訊息的來源且沒有觸發者(clock):
    setup_channel(config(timer_id=7, message="{channel} 開台 {uptime} {user}", interval=5))
    clock.now += 300
    run(timers.tick())
    args, kwargs = speech.say.await_args
    assert args[:3] == (LOGIN, TWITCH_ID, "{channel} 開台 {uptime} {user}")
    ctx = args[3]
    assert (ctx.twitch_id, ctx.channel, ctx.user, ctx.args, ctx.count) == (TWITCH_ID, LOGIN, None, None, None)
    assert kwargs == {"source_kind": "timer", "source_key": "7"}


def test_發送後重新計時_每個間隔發一次(clock):
    setup_channel(config(interval=5))
    for expected in (1, 2, 3):
        clock.now += 300
        run(timers.tick())
        run(timers.tick())  # 同一時間再檢查不會重複發
        assert speech.say.await_count == expected


def test_發送失敗或被擋下也重新計時(clock):
    speech.say.return_value = False
    setup_channel(config(interval=5))
    clock.now += 300
    run(timers.tick())
    clock.now += 30
    run(timers.tick())
    assert speech.say.await_count == 1


def test_沒開台不發_下播後停止_再開台重新計時(clock):
    setup_channel(config(interval=5), online=False)
    timers._online[TWITCH_ID] = False
    clock.now += 3000
    run(timers.tick())
    speech.say.assert_not_awaited()

    run(timers.on_stream_online(TWITCH_ID))
    clock.now += 300
    run(timers.tick())
    assert speech.say.await_count == 1

    run(timers.on_stream_offline(TWITCH_ID))
    clock.now += 3000
    run(timers.tick())
    assert speech.say.await_count == 1

    run(timers.on_stream_online(TWITCH_ID))
    clock.now += 299
    run(timers.tick())
    assert speech.say.await_count == 1  # 從再次開台起算
    clock.now += 1
    run(timers.tick())
    assert speech.say.await_count == 2


def test_每則計時訊息各自的間隔(clock):
    setup_channel(config(1, "a", interval=5), config(2, "b", interval=10))
    clock.now += 300
    run(timers.tick())
    assert [c.args[2] for c in speech.say.await_args_list] == ["a"]
    clock.now += 300
    run(timers.tick())
    assert sorted(c.args[2] for c in speech.say.await_args_list) == ["a", "a", "b"]


def test_同一次檢查多則到期各自獨立照發(clock):
    setup_channel(config(1, "a", interval=5), config(2, "b", interval=5), config(3, "c", interval=5))
    clock.now += 300
    run(timers.tick())
    assert [c.args[2] for c in speech.say.await_args_list] == ["a", "b", "c"]


def test_只有在聊天室的頻道會發送(clock):
    setup_channel(config(), twitch_id=OTHER_ID)  # OTHER_ID 不在 rooms
    clock.now += 3000
    run(timers.tick())
    speech.say.assert_not_awaited()
    assert OTHER_ID not in timers._configs  # 離開聊天室的頻道狀態一併清掉


def test_一個頻道出錯不影響其他頻道(clock, monkeypatch):
    monkeypatch.setattr(channels, "rooms", {TWITCH_ID: LOGIN, OTHER_ID: "other"})
    setup_channel(config(1, "壞的"), twitch_id=TWITCH_ID)
    setup_channel(config(2, "好的"), twitch_id=OTHER_ID)
    speech.say.side_effect = [RuntimeError("boom"), True]
    clock.now += 600
    run(timers.tick())
    assert [c.args[2] for c in speech.say.await_args_list] == ["壞的", "好的"]


# ── 最少聊天量 ──


def test_最少聊天量_時間到但不足不發_第_10_則立刻發_bot_不計入(clock):
    setup_channel(config(interval=5, lines=10))
    clock.now += 300

    async def chat():
        for _ in range(9):
            await timers.on_chat_message(TWITCH_ID, False)
            await timers.on_chat_message(TWITCH_ID, True)  # bot 自己的訊息不計入
        await timers.tick()
        await asyncio.sleep(0)
        assert speech.say.await_count == 0
        await timers.on_chat_message(TWITCH_ID, False)
        await asyncio.sleep(0)
        assert speech.say.await_count == 1

    run(chat())
    assert timers._runtime[(TWITCH_ID, 1)].lines == 0


def test_聊天量夠但間隔未到不發_間隔一到就發(clock):
    setup_channel(config(interval=5, lines=3))

    async def chat():
        for _ in range(5):
            await timers.on_chat_message(TWITCH_ID, False)
        await asyncio.sleep(0)
        assert speech.say.await_count == 0
        clock.now += 300
        await timers.tick()
        assert speech.say.await_count == 1

    run(chat())


def test_發送後聊天數歸零要重新累積(clock):
    setup_channel(config(interval=5, lines=2))

    async def chat():
        clock.now += 300
        for _ in range(2):
            await timers.on_chat_message(TWITCH_ID, False)
        await asyncio.sleep(0)
        assert speech.say.await_count == 1
        clock.now += 300
        await timers.on_chat_message(TWITCH_ID, False)
        await asyncio.sleep(0)
        assert speech.say.await_count == 1  # 只有 1 則，還不夠
        await timers.on_chat_message(TWITCH_ID, False)
        await asyncio.sleep(0)
        assert speech.say.await_count == 2

    run(chat())


def test_沒開台時的聊天不計數(clock):
    setup_channel(config(interval=5, lines=1), online=False)
    timers._online[TWITCH_ID] = False

    async def chat():
        for _ in range(5):
            await timers.on_chat_message(TWITCH_ID, False)
        await timers.on_stream_online(TWITCH_ID)
        assert timers._runtime[(TWITCH_ID, 1)].lines == 0

    run(chat())


def test_沒有最少聊天量時聊天不會提早發送(clock):
    setup_channel(config(interval=5, lines=0))

    async def chat():
        await timers.on_chat_message(TWITCH_ID, False)
        await asyncio.sleep(0)

    run(chat())
    speech.say.assert_not_awaited()


# ── 關閉、刪除與設定重讀 ──


def test_關閉的計時訊息不發_其他不受影響(clock):
    setup_channel(config(1, "關的", enabled=False), config(2, "開的"))
    clock.now += 600
    run(timers.tick())
    assert [c.args[2] for c in speech.say.await_args_list] == ["開的"]


def add(repo, twitch_id=TWITCH_ID, **kwargs):
    kwargs.setdefault("message", "m")
    kwargs.setdefault("interval_minutes", 5)
    return repo.save_twitch_timer(TwitchTimer(twitch_id=twitch_id, **kwargs))


def test_失效通知後重讀_關閉的立刻停止_新增的從現在起算(clock, repo):
    first = add(repo, message="a")
    run(timers.on_stream_online(TWITCH_ID))
    run(timers._on_invalidated(str(TWITCH_ID)))
    clock.now += 200
    second = add(repo, message="b")
    run(timers._on_invalidated(str(TWITCH_ID)))
    clock.now += 100  # first 滿 300 秒，second 才過 100 秒
    run(timers.tick())
    assert [c.args[2] for c in speech.say.await_args_list] == ["a"]

    first.enabled = False
    repo.save_twitch_timer(first)
    run(timers._on_invalidated(str(TWITCH_ID)))
    assert (TWITCH_ID, first.id) not in timers._runtime
    clock.now += 200
    run(timers.tick())
    assert [c.args[2] for c in speech.say.await_args_list] == ["a", "b"]
    assert second.id is not None


def test_刪除的計時訊息丟掉狀態(clock, repo):
    row = add(repo)
    run(timers.on_stream_online(TWITCH_ID))
    run(timers._on_invalidated(str(TWITCH_ID)))
    assert (TWITCH_ID, row.id) in timers._runtime
    repo.delete_twitch_timer(TWITCH_ID, row.id)
    run(timers._on_invalidated(str(TWITCH_ID)))
    assert timers._runtime == {}


def test_改間隔保留計時狀態_依新間隔判斷(clock, repo):
    row = add(repo, interval_minutes=60)
    run(timers.on_stream_online(TWITCH_ID))
    run(timers._on_invalidated(str(TWITCH_ID)))
    clock.now += 600
    row.interval_minutes = 10
    repo.save_twitch_timer(row)
    run(timers._on_invalidated(str(TWITCH_ID)))
    run(timers.tick())
    assert speech.say.await_count == 1


def test_key_為_None_重讀所有在聊天室的頻道_不在聊天室的失效通知忽略(clock, repo, monkeypatch):
    add(repo, message="host")
    add(repo, twitch_id=OTHER_ID, message="other")
    run(timers._on_invalidated(None))
    assert [c.message for c in timers._configs[TWITCH_ID]] == ["host"]
    assert OTHER_ID not in timers._configs
    run(timers._on_invalidated(str(OTHER_ID)))
    assert OTHER_ID not in timers._configs


def test_tick_載入還沒讀過的頻道(clock, repo):
    add(repo, message="從資料庫來", interval_minutes=5)
    timers._online[TWITCH_ID] = True
    run(timers.tick())  # 載入並從現在起算
    clock.now += 300
    run(timers.tick())
    assert speech.say.await_args.args[2] == "從資料庫來"


# ── bot 重啟時開台狀態未知 ──


def _prepare_returns(stream):
    async def prepare(template, ctx):
        ctx.stream = stream
        return ctx

    speech.prepare.side_effect = prepare


def test_不知道開台狀態時只查一次_直播中的頻道從現在起算(clock):
    stream = speech.StreamInfo(datetime.now(UTC), "遊戲", "標題")
    _prepare_returns(stream)
    timers._apply(TWITCH_ID, [config(interval=5)])
    run(timers.tick())
    speech.say.assert_not_awaited()
    clock.now += 300
    run(timers.tick())
    assert speech.say.await_count == 1
    assert speech.prepare.await_count == 1
    assert speech.prepare.await_args.args[0] == "{uptime}"


def test_查到沒開台就不發_也不重複查(clock):
    _prepare_returns(None)
    timers._apply(TWITCH_ID, [config(interval=5)])
    for _ in range(3):
        clock.now += 300
        run(timers.tick())
    speech.say.assert_not_awaited()
    assert speech.prepare.await_count == 1


def test_沒有啟用的計時訊息就不查_Helix(clock):
    timers._apply(TWITCH_ID, [config(enabled=False)])
    run(timers.tick())
    speech.prepare.assert_not_awaited()


def test_第一次_tick_前就開台_之後照常載入設定並發送(clock, repo):
    add(repo, message="從資料庫來", interval_minutes=5)
    run(timers.on_stream_online(TWITCH_ID))  # 設定還沒載入過
    assert TWITCH_ID not in timers._configs
    run(timers.tick())  # 載入，並從現在起算
    clock.now += 300
    run(timers.tick())
    assert speech.say.await_args.args[2] == "從資料庫來"


def test_查開台狀態途中收到下播事件_不被舊的查詢結果蓋掉(clock):
    timers._apply(TWITCH_ID, [config(interval=5)])

    async def prepare(template, ctx):
        await timers.on_stream_offline(TWITCH_ID)  # 查詢途中收到下播
        ctx.stream = speech.StreamInfo(datetime.now(UTC), "遊戲", "標題")  # 查詢回來還是舊的「開台」
        return ctx

    speech.prepare.side_effect = prepare
    run(timers.tick())
    assert timers._online[TWITCH_ID] is False
    clock.now += 3000
    run(timers.tick())
    speech.say.assert_not_awaited()


def test_查開台狀態途中收到開台事件_保留事件的結果(clock):
    timers._apply(TWITCH_ID, [config(interval=5)])

    async def prepare(template, ctx):
        await timers.on_stream_online(TWITCH_ID)  # 查詢途中收到開台
        clock.now += 100
        ctx.stream = None  # 查詢回來是舊的「沒開台」
        return ctx

    speech.prepare.side_effect = prepare
    run(timers.tick())
    assert timers._online[TWITCH_ID] is True
    clock.now += 200  # 從開台事件起算 300 秒
    run(timers.tick())
    assert speech.say.await_count == 1


def test_查開台狀態途中頻道被忘掉_不把設定寫成空清單(clock, repo):
    add(repo, message="從資料庫來", interval_minutes=5)
    timers._apply(TWITCH_ID, timers._load(TWITCH_ID))

    async def prepare(template, ctx):
        timers._forget(TWITCH_ID)  # 查詢途中頻道離開聊天室並收到失效通知
        ctx.stream = speech.StreamInfo(datetime.now(UTC), "遊戲", "標題")
        return ctx

    speech.prepare.side_effect = prepare
    run(timers.tick())
    assert TWITCH_ID not in timers._configs and TWITCH_ID not in timers._online

    speech.prepare.side_effect = None
    _prepare_returns(speech.StreamInfo(datetime.now(UTC), "遊戲", "標題"))
    run(timers.tick())  # 下一次 tick 重新載入設定並查開台
    clock.now += 300
    run(timers.tick())
    assert speech.say.await_args.args[2] == "從資料庫來"


# ── 啟動、重啟與收尾 ──


@pytest.fixture
def scheduler(monkeypatch):
    """換掉排程與失效註冊：記下每次排程在哪個 loop、被取消沒有。"""
    monkeypatch.setattr(timers, "_ticker", None)
    monkeypatch.setattr(timers, "_ticker_loop", None)
    scheduled: list[tuple[object, MagicMock]] = []

    def fake_run(coro, loop):
        coro.close()
        future = MagicMock()
        scheduled.append((loop, future))
        return future

    monkeypatch.setattr(timers.asyncio, "run_coroutine_threadsafe", fake_run)
    registered: list[tuple[str, object]] = []
    monkeypatch.setattr(
        timers.cache_invalidation, "on_invalidate", lambda cache, handler, loop: registered.append((cache, loop))
    )
    return scheduled, registered


def test_start_註冊失效_handler_並開始排程(scheduler, monkeypatch):
    scheduled, registered = scheduler
    loop = object()
    monkeypatch.setattr(timers.state, "loop", loop, raising=False)
    chat = MagicMock()
    timers.start(chat)
    assert registered == [("twitch_timer", loop)]
    assert [s[0] for s in scheduled] == [loop]
    assert chat.register_event.call_args.args[1] is timers._on_ready


def test_Chat_重啟換_loop_時改綁並重起排程_同一個_loop_不重複(scheduler):
    scheduled, registered = scheduler
    old, new = object(), object()
    timers._bind(old)
    timers._bind(old)
    assert len(scheduled) == 1
    timers._bind(new)
    assert [s[0] for s in scheduled] == [old, new]
    scheduled[0][1].cancel.assert_called_once()
    assert [r[1] for r in registered] == [old, old, new]


def test_舊_loop_已關閉時取消不會出錯(scheduler):
    scheduled, _ = scheduler
    timers._bind(object())
    scheduled[0][1].cancel.side_effect = RuntimeError("loop closed")
    timers._bind(object())
    assert len(scheduled) == 2


def test_stop_取消排程(scheduler):
    scheduled, _ = scheduler
    timers._bind(object())
    timers.stop()
    scheduled[0][1].cancel.assert_called_once()
    timers.stop()  # 再停一次沒有影響


def test_on_ready_在新_loop_上改綁(scheduler):
    scheduled, _ = scheduler
    timers._bind(object())

    async def ready():
        await timers._on_ready(SimpleNamespace())
        return asyncio.get_running_loop()

    loop = run(ready())
    assert scheduled[-1][0] is loop
