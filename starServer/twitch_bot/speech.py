"""bot 在聊天室發言的共用管線：模板變數代入、發言前的 AutoMod 檢查、擋下紀錄。

自訂指令（W-05）、計時訊息（W-06）與事件回應（W-07）都只透過這裡發言：
組一個 `SpeechContext`，呼叫 `say(...)`；開台資訊與 `{game}`、`{title}` 的查詢也在這裡，呼叫端不用管。
"""

import asyncio
import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from twitchAPI.chat import ChatMessage, EventData
from twitchAPI.helper import first

from starlib.database import sqldb
from starlib.messaging import cache_invalidation
from starlib.twitch_speech_check import check_text, substitute, uses_viewer_input, variables_used
from starServer.twitch_bot import state

log = logging.getLogger(__name__)

#: Twitch 單則訊息上限
MAX_MESSAGE_LENGTH = 500
#: {game}、{title} 的查詢結果快取秒數
CHANNEL_INFO_TTL = 60.0
#: 發言前 AutoMod 檢查結果的快取秒數
CHECK_TTL = 600.0
#: 查不到分類與標題時代入的文字
UNKNOWN = "未知"
NOT_LIVE = "未開台"

type SourceKind = Literal["command", "timer", "event_response"]


@dataclass(frozen=True, slots=True)
class StreamInfo:
    started_at: datetime
    game: str
    title: str


@dataclass(frozen=True, slots=True)
class ChannelInfo:
    game: str
    title: str


@dataclass(slots=True)
class SpeechContext:
    """代入模板用的資料。沒提供的欄位（例如計時訊息沒有觸發者）對應的變數會原樣保留。

    stream 與 channel_info 不必填：`say` 發言時依模板用到的變數自動查（`prepare`）。
    """

    twitch_id: int
    #: 頻道的顯示名稱，`{channel}` 用
    channel: str
    user: str | None = None
    args: str | None = None
    count: int | None = None
    #: 事件變數：months、amount、viewers
    event: Mapping[str, str] = field(default_factory=dict)
    stream: StreamInfo | None = None
    channel_info: ChannelInfo | None = None
    now: datetime = field(default_factory=lambda: datetime.now(UTC))
    stream_lookup_failed: bool = False


# ── 開台資訊 ──────────────────────────────────────────────

#: 已知的開台狀態：有鍵代表知道，值是 None 代表確定沒開台；沒有鍵代表還不知道
_live: dict[int, StreamInfo | None] = {}


def set_live(twitch_id: int, stream: StreamInfo) -> None:
    """頻道開台時由 events.py 呼叫。"""
    _live[twitch_id] = stream


def set_offline(twitch_id: int) -> None:
    """頻道下播時由 events.py 呼叫。"""
    _live[twitch_id] = None


def current_stream(twitch_id: int) -> StreamInfo | None:
    """目前已知的開台資訊；還不知道時回 None。"""
    return _live.get(twitch_id)


async def _resolve_stream(twitch_id: int) -> StreamInfo | None:
    """已知就直接用；還不知道（例如 bot 剛啟動）就用 Helix get_streams 查一次並記下。"""
    if twitch_id in _live:
        return _live[twitch_id]
    try:
        live = await first(state.twitch.get_streams(user_id=[str(twitch_id)]))
    except Exception:
        log.warning("查詢 %s 的開台狀態失敗", twitch_id, exc_info=True)
        return None
    info = StreamInfo(live.started_at, live.game_name, live.title) if live else None
    _live[twitch_id] = info
    return info


# ── 分類與標題 ────────────────────────────────────────────

_channel_info: dict[int, tuple[float, ChannelInfo]] = {}
_channel_info_pending: dict[int, object] = {}


async def _resolve_channel_info(twitch_id: int) -> ChannelInfo | None:
    cached = _channel_info.get(twitch_id)
    if cached is not None and time.monotonic() - cached[0] < CHANNEL_INFO_TTL:
        return cached[1]
    marker = _channel_info_pending[twitch_id] = object()
    try:
        [result, *_] = await state.twitch.get_channel_information(str(twitch_id))
        info = ChannelInfo(result.game_name, result.title)
        if _channel_info_pending.get(twitch_id) is marker:
            _channel_info[twitch_id] = (time.monotonic(), info)
        return info
    except Exception:
        log.warning("查詢 %s 的頻道資訊失敗", twitch_id, exc_info=True)
        fallback = _channel_info.get(twitch_id)
        return fallback[1] if fallback else None
    finally:
        if _channel_info_pending.get(twitch_id) is marker:
            _channel_info_pending.pop(twitch_id, None)


def forget_channel_info(twitch_id: int) -> None:
    """頻道的標題或分類剛被改過，丟掉 `{game}`、`{title}` 的快取。"""
    _channel_info.pop(twitch_id, None)
    _channel_info_pending.pop(twitch_id, None)


async def _on_stream_info_invalidated(key: str | None) -> None:
    if key is None:
        _channel_info.clear()
        _channel_info_pending.clear()
    else:
        forget_channel_info(int(key))


async def on_ready(_: EventData) -> None:
    cache_invalidation.on_invalidate("twitch_stream_info", _on_stream_info_invalidated, asyncio.get_running_loop())


# ── 代入 ──────────────────────────────────────────────────


def _uptime(stream: StreamInfo | None, now: datetime) -> str:
    if stream is None:
        return NOT_LIVE
    minutes = max(int((now - stream.started_at).total_seconds() // 60), 0)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours} 小時 {minutes} 分"
    return f"{minutes} 分" if minutes else "不到 1 分鐘"


def _values(ctx: SpeechContext) -> dict[str, str]:
    values = dict(ctx.event)
    values["channel"] = ctx.channel
    values["uptime"] = UNKNOWN if ctx.stream_lookup_failed else _uptime(ctx.stream, ctx.now)
    values["game"] = ctx.channel_info.game if ctx.channel_info else UNKNOWN
    values["title"] = ctx.channel_info.title if ctx.channel_info else UNKNOWN
    if ctx.user is not None:
        values["user"] = ctx.user
    if ctx.args is not None:
        values["args"] = ctx.args
    if ctx.count is not None:
        values["count"] = str(ctx.count)
    # {touser}：參數的第一個字（去掉 @），沒有參數就是觸發者
    target = ctx.args.split(maxsplit=1)[0].removeprefix("@") if ctx.args and ctx.args.strip() else ctx.user
    if target is not None:
        values["touser"] = target
    return values


def render(template: str, ctx: SpeechContext) -> str:
    """把模板的變數換成 ctx 的內容。不認得、或 ctx 沒提供的變數原樣保留；沒開台時 `{uptime}` 是「未開台」。"""
    return substitute(template, _values(ctx))


async def prepare(template: str, ctx: SpeechContext) -> SpeechContext:
    """依模板用到的變數補上開台資訊與分類標題；沒用到就不查 Helix。"""
    used = variables_used(template)
    if "uptime" in used and ctx.stream is None:
        ctx.stream = await _resolve_stream(ctx.twitch_id)
        ctx.stream_lookup_failed = ctx.stream is None and ctx.twitch_id not in _live
    if used & {"game", "title"} and ctx.channel_info is None:
        ctx.channel_info = await _resolve_channel_info(ctx.twitch_id)
    return ctx


# ── 發言 ──────────────────────────────────────────────────

#: (頻道, 文字) -> (檢查時間, 是否通過)；只存確定的結果，檢查失敗不存
_check_cache: dict[tuple[int, str], tuple[float, bool]] = {}


async def check(twitch_id: int, text: str) -> Literal["ok", "blocked", "unavailable"]:
    """頻道 AutoMod 對一段文字的判定（含快取）；`say` 與直接發言的指令共用。"""
    key = (twitch_id, text)
    cached = _check_cache.get(key)
    if cached is not None and time.monotonic() - cached[0] < CHECK_TTL:
        return "ok" if cached[1] else "blocked"
    result = await check_text(twitch_id, text)
    if result != "unavailable":
        now = time.monotonic()
        for stale in [k for k, (at, _) in _check_cache.items() if now - at >= CHECK_TTL]:
            del _check_cache[stale]
        _check_cache[key] = (now, result == "ok")
    return result


def _write_block(twitch_id: int, source_kind: str, source_key: str, text: str, reason: str) -> None:
    try:
        sqldb.add_twitch_automod_block(twitch_id, source_kind, source_key, text, reason)
    finally:
        sqldb.release_session()


async def say(
    channel: str,
    twitch_id: int,
    template: str,
    ctx: SpeechContext,
    *,
    source_kind: SourceKind,
    source_key: str,
    reply_to: ChatMessage | None = None,
) -> bool:
    """代入模板並在聊天室發言，回傳是否送出。不 raise。

    只有內容帶入觀眾輸入（模板含 `{touser}`、`{args}`）的訊息才在發言前檢查頻道 AutoMod；
    其他模板在實況主儲存時已檢查過，直接送出。被擋下或檢查失敗（含超出限制）時不送出，寫進擋下紀錄。
    channel 是聊天室名稱（login）；reply_to 有值時以回覆的方式發言。
    """
    try:
        ctx = await prepare(template, ctx)
        text = render(template, ctx)[:MAX_MESSAGE_LENGTH]
        if not text.strip():
            return False
        if uses_viewer_input(template):
            result = await check(twitch_id, text)
            if result != "ok":
                reason = "automod" if result == "blocked" else "check_failed"
                await asyncio.to_thread(_write_block, twitch_id, source_kind, source_key, text, reason)
                return False
        if reply_to is not None:
            await reply_to.reply(text)
        else:
            await state.chat.send_message(channel, text)
        return True
    except Exception:
        log.exception("%s 的發言失敗（%s %s）", twitch_id, source_kind, source_key)
        return False
