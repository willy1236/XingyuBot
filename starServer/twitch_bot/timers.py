"""計時訊息：開台中依設定的間隔與最少聊天量，在聊天室定時發言。

每個頻道的每則計時訊息各有「上次發送時間」與「自上次發送後的聊天數」。開台後第一則等滿一個間隔，
下播後停止，再次開台重新計時；間隔到了但聊天數不足時等，第 N 則聊天一到就立刻發。
bot 自己的訊息不計入。發送一律經 `speech.say`（變數代入與 AutoMod 檢查都在那裡）。

設定由 `twitch_timer` 快取失效（Pub/Sub）通知重讀；狀態與設定只在 Chat 的 event loop 上存取，不需要鎖。
Chat 重啟換 loop 時，READY 會把失效 handler 與排程改綁到新的 loop。
"""

import asyncio
import concurrent.futures
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from twitchAPI.chat import Chat, ChatEvent, EventData

from starlib.database import sqldb
from starlib.messaging import cache_invalidation
from starServer.twitch_bot import speech, state

log = logging.getLogger(__name__)

#: 檢查有沒有到期的間隔（秒）
TICK_SECONDS = 30.0

#: 現在的時間（秒，monotonic）；測試可以換掉
_now: Callable[[], float] = time.monotonic


@dataclass(frozen=True, slots=True)
class TimerConfig:
    """一則計時訊息的設定（與資料庫 session 無關的複本）。"""

    id: int
    message: str
    interval_minutes: int
    min_chat_lines: int
    enabled: bool


@dataclass(slots=True)
class _Runtime:
    last_sent: float
    lines: int = 0


#: twitch_id -> 該頻道的計時訊息設定；沒有鍵代表還沒載入
_configs: dict[int, list[TimerConfig]] = {}
#: (twitch_id, timer_id) -> 發送狀態；只有開台中且啟用的計時訊息才有
_runtime: dict[tuple[int, int], _Runtime] = {}
#: twitch_id -> 是否開台；沒有鍵代表還不知道（bot 剛啟動），tick 時查一次
_online: dict[int, bool] = {}

_ticker: concurrent.futures.Future | None = None
_ticker_loop: asyncio.AbstractEventLoop | None = None
#: 立刻發送的背景工作，留著參照免得被回收
_sending: set[asyncio.Task] = set()


def _rooms() -> dict[int, str]:
    """目前應在聊天室的頻道：twitch_id -> login。channels 會 import events，events 又 import 本模組，所以在用到時才 import。"""
    from starServer.twitch_bot import channels

    return channels.rooms


# ── 啟動與收尾 ────────────────────────────────────────────


def start(chat: Chat) -> None:
    """Twitch bot 初始化完成後呼叫一次：註冊 `twitch_timer` 的快取失效 handler，並開始每 30 秒檢查。

    Chat 重啟後 READY 會在新的 loop 上再來一次，這時 handler 與排程都要改綁到新的 loop。
    """
    _bind(state.loop)
    chat.register_event(ChatEvent.READY, _on_ready)


def stop() -> None:
    """Twitch bot 收尾時呼叫：停止排程。"""
    _stop_ticker()


async def _on_ready(_: EventData) -> None:
    _bind(asyncio.get_running_loop())


def _bind(loop: asyncio.AbstractEventLoop) -> None:
    cache_invalidation.on_invalidate("twitch_timer", _on_invalidated, loop)
    if _ticker is None or _ticker_loop is not loop:
        _stop_ticker()
        _start_ticker(loop)


def _start_ticker(loop: asyncio.AbstractEventLoop) -> None:
    global _ticker, _ticker_loop
    _ticker = asyncio.run_coroutine_threadsafe(_run(), loop)
    _ticker_loop = loop


def _stop_ticker() -> None:
    global _ticker, _ticker_loop
    if _ticker is not None:
        try:
            _ticker.cancel()
        except RuntimeError:  # 舊的 loop 已經關閉，排程跟著結束了
            log.debug("舊 loop 已關閉，計時訊息的排程不需取消")
    _ticker = None
    _ticker_loop = None


async def _run() -> None:
    while True:
        await asyncio.sleep(TICK_SECONDS)
        try:
            await tick()
        except Exception:
            log.exception("計時訊息的檢查失敗")


# ── 設定 ──────────────────────────────────────────────────


def _load(twitch_id: int) -> list[TimerConfig]:
    try:
        return [
            TimerConfig(t.id, t.message, t.interval_minutes, t.min_chat_lines, t.enabled)
            for t in sqldb.list_twitch_timers(twitch_id)
            if t.id is not None
        ]
    finally:
        sqldb.release_session()


def _apply(twitch_id: int, configs: list[TimerConfig]) -> None:
    """換上最新的設定：刪除或關閉的計時訊息丟掉狀態，開台中新出現或剛開啟的從現在起算一個間隔。"""
    _configs[twitch_id] = configs
    enabled = {c.id for c in configs if c.enabled}
    for key in [k for k in _runtime if k[0] == twitch_id and k[1] not in enabled]:
        del _runtime[key]
    if _online.get(twitch_id):
        for timer_id in enabled:
            _runtime.setdefault((twitch_id, timer_id), _Runtime(_now()))


def _forget(twitch_id: int) -> None:
    _configs.pop(twitch_id, None)
    _online.pop(twitch_id, None)
    for key in [k for k in _runtime if k[0] == twitch_id]:
        del _runtime[key]


async def _on_invalidated(key: str | None) -> None:
    """計時訊息改了（後台，任何一個實例）：重讀該頻道，key 為 None 時重讀全部。"""
    rooms = _rooms()
    if key is None:
        ids = list(rooms)
    else:
        ids = [int(key)]
        if ids[0] not in rooms:  # 不在聊天室的頻道不需要設定，加入時再載入
            _forget(ids[0])
            return
    for twitch_id in ids:
        _apply(twitch_id, await asyncio.to_thread(_load, twitch_id))


# ── 開台、下播與聊天數 ────────────────────────────────────


async def on_stream_online(twitch_id: int) -> None:
    """確認頻道開台後呼叫：所有計時訊息從現在起算，開台後第一則等滿一個間隔。"""
    _online[twitch_id] = True
    for key in [k for k in _runtime if k[0] == twitch_id]:
        del _runtime[key]
    # 設定還沒載入過就不動：下一次 tick 會載入，並因為已開台而從那時起算
    if twitch_id in _configs:
        _apply(twitch_id, _configs[twitch_id])


async def on_stream_offline(twitch_id: int) -> None:
    """頻道下播時呼叫：停止發送，狀態清掉，下次開台重新計時。"""
    _online[twitch_id] = False
    for key in [k for k in _runtime if k[0] == twitch_id]:
        del _runtime[key]


async def on_chat_message(twitch_id: int, is_bot: bool) -> None:
    """頻道收到一則聊天室訊息時呼叫；is_bot 表示發言者是 bot 自己，不計入。

    計入之後若有計時訊息因此達到最少聊天量（間隔已到），立刻發送，不等下一次檢查。
    """
    if is_bot or not _online.get(twitch_id):
        return
    login = _rooms().get(twitch_id)
    for config in _configs.get(twitch_id, []):
        runtime = _runtime.get((twitch_id, config.id))
        if runtime is None:
            continue
        runtime.lines += 1
        if login is not None and _due(config, runtime, _now()):
            _mark_sent(runtime)
            task = asyncio.ensure_future(_say(twitch_id, login, config))
            _sending.add(task)
            task.add_done_callback(_sending.discard)


# ── 檢查與發送 ────────────────────────────────────────────


def _due(config: TimerConfig, runtime: _Runtime, now: float) -> bool:
    return (
        config.enabled
        and now - runtime.last_sent >= config.interval_minutes * 60
        and runtime.lines >= config.min_chat_lines
    )


def _mark_sent(runtime: _Runtime) -> None:
    """發送前先重新計時：不論 `say` 成功與否都等下一個間隔，被 AutoMod 擋下時才不會每次檢查都重試。"""
    runtime.last_sent = _now()
    runtime.lines = 0


async def _say(twitch_id: int, login: str, config: TimerConfig) -> None:
    # 計時訊息沒有觸發者，{user}、{touser}、{args}、{count} 不提供，原樣保留
    ctx = speech.SpeechContext(twitch_id=twitch_id, channel=login)
    await speech.say(login, twitch_id, config.message, ctx, source_kind="timer", source_key=str(config.id))


async def _resolve_online(twitch_id: int, login: str) -> bool:
    """bot 剛啟動、還不知道頻道有沒有開台時查一次（`speech.prepare` 會用 Helix 查並記下）。"""
    ctx = speech.SpeechContext(twitch_id=twitch_id, channel=login)
    await speech.prepare("{uptime}", ctx)
    return ctx.stream is not None


async def _check_channel(twitch_id: int, login: str) -> None:
    if twitch_id not in _configs:
        _apply(twitch_id, await asyncio.to_thread(_load, twitch_id))
    if not any(c.enabled for c in _configs[twitch_id]):
        return
    if twitch_id not in _online:
        online = await _resolve_online(twitch_id, login)
        if twitch_id not in _configs:  # 查詢途中頻道被忘掉了（離開聊天室），下次 tick 再重新載入
            return
        # 查詢途中若已收到開台或下播事件，以事件為準，不被可能已過時的查詢結果蓋掉
        if twitch_id not in _online:
            _online[twitch_id] = online
            _apply(twitch_id, _configs[twitch_id])
    if not _online[twitch_id]:
        return
    now = _now()
    for config in _configs[twitch_id]:
        runtime = _runtime.get((twitch_id, config.id))
        if runtime is not None and _due(config, runtime, now):
            _mark_sent(runtime)
            await _say(twitch_id, login, config)


async def tick() -> None:
    """檢查每個在聊天室的頻道，到期的計時訊息各自發送；某個頻道出錯不影響其他頻道。"""
    rooms = _rooms()
    for twitch_id in [i for i in _configs if i not in rooms]:  # 已離開聊天室的頻道
        _forget(twitch_id)
    for twitch_id, login in list(rooms.items()):
        try:
            await _check_channel(twitch_id, login)
        except Exception:
            log.exception("%s 的計時訊息檢查失敗", twitch_id)
