"""聊天室過濾、執法、Raid 暫停與暫時放行。執行期狀態只由 Chat loop 存取。"""

import asyncio
import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from weakref import WeakValueDictionary

from aiohttp import ClientError
from sqlalchemy.exc import SQLAlchemyError
from twitchAPI.chat import ChatCommand, ChatMessage, EventData
from twitchAPI.helper import first
from twitchAPI.type import TwitchAPIException

from starlib import twitch_moderation
from starlib.database import TwitchEnforcementLog, sqldb
from starlib.messaging import cache_invalidation, rpc
from starlib.twitch_moderation import FilterConfig, ModerationConfig, Stage
from starlib.twitch_speech_check import substitute
from starServer.twitch_bot import state
from starServer.twitch_bot.helix import TwitchStatusError
from starServer.twitch_bot.viewers import PERMISSION_LEVELS, viewer_level

log = logging.getLogger(__name__)
_now: Callable[[], float] = time.monotonic
_RAID_PAUSED_FILTERS = frozenset({"emote", "repetition", "duplicate", "caps"})


@dataclass(slots=True)
class _RecentMessages:
    messages: deque[tuple[float, tuple[int, str]]] = field(default_factory=deque)
    counts: dict[tuple[int, str], int] = field(default_factory=dict)

    def clear(self) -> None:
        self.messages.clear()
        self.counts.clear()

    def expire(self, cutoff: float) -> None:
        while self.messages and self.messages[0][0] < cutoff:
            _, key = self.messages.popleft()
            count = self.counts[key] - 1
            if count:
                self.counts[key] = count
            else:
                del self.counts[key]

    def add(self, now: float, user_id: int, text: str) -> int:
        key = (user_id, text.strip().casefold())
        self.messages.append((now, key))
        count = self.counts.get(key, 0) + 1
        self.counts[key] = count
        return count


@dataclass(slots=True)
class _Channel:
    config: ModerationConfig | None = None
    config_generation: int = 0
    config_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    enforcement_locks: WeakValueDictionary[int, asyncio.Lock] = field(default_factory=WeakValueDictionary)
    strikes: dict[tuple[int, str], tuple[int, float]] = field(default_factory=dict)
    permits: dict[int, float] = field(default_factory=dict)
    notices: dict[str, float] = field(default_factory=dict)
    recent_messages: _RecentMessages = field(default_factory=_RecentMessages)
    next_prune: float = 0.0
    pause_until: float = 0.0

    def invalidate_config(self) -> None:
        self.config_generation += 1
        self.config = None

    def prune(self, now: float, strike_window: int) -> None:
        if now < self.next_prune:
            return
        self.next_prune = now + 60
        self.strikes = {key: value for key, value in self.strikes.items() if now - value[1] <= strike_window}
        self.permits = {key: until for key, until in self.permits.items() if now < until}


_channels: dict[int, _Channel] = {}
_loop: asyncio.AbstractEventLoop | None = None


def forget_channel(twitch_id: int) -> None:
    _channels.pop(twitch_id, None)


async def _on_invalidated(key: str | None) -> None:
    if key is None:
        for runtime in _channels.values():
            runtime.invalidate_config()
    else:
        runtime = _channels.get(int(key))
        if runtime is not None:
            runtime.invalidate_config()


def register(loop: asyncio.AbstractEventLoop) -> None:
    """註冊聊天室管理的 RPC，handler 在 `loop` 上執行。

    啟動設定時先綁到當下的 loop；Chat 的 READY（含重啟後換 loop）再綁到 Chat 的 loop，之後狀態只由 Chat loop 存取。
    """
    rpc.handle("moderation.lift", lift, loop)
    rpc.handle("moderation.clear_strikes", clear_strikes, loop)


async def on_ready(_: EventData) -> None:
    global _loop
    loop = asyncio.get_running_loop()
    if _loop is not loop:
        for runtime in _channels.values():
            runtime.config_lock = asyncio.Lock()
            runtime.enforcement_locks.clear()
        _loop = loop
    cache_invalidation.on_invalidate("twitch_moderation", _on_invalidated, loop)
    register(loop)
    await _on_invalidated(None)


def _read_config(twitch_id: int) -> ModerationConfig:
    try:
        return twitch_moderation.get_config(twitch_id)
    finally:
        sqldb.release_session()


async def _config(twitch_id: int, runtime: _Channel) -> ModerationConfig:
    async with runtime.config_lock:
        while runtime.config is None:
            generation = runtime.config_generation
            config = await asyncio.to_thread(_read_config, twitch_id)
            if generation == runtime.config_generation:
                runtime.config = config
        return runtime.config


def _enabled(twitch_id: int) -> bool:
    row = state.join_channels.get(twitch_id)
    return row is not None and row.state == "enabled"


async def _start_raid_pause(twitch_id: int, received_at: float) -> None:
    if not _enabled(twitch_id):
        return
    runtime = _channels.get(twitch_id)
    if runtime is None:
        runtime = _channels[twitch_id] = _Channel()
    config = await _config(twitch_id, runtime)
    if _channels.get(twitch_id) is runtime:
        runtime.pause_until = received_at + config["settings"]["raid_pause_seconds"]


async def on_raid(twitch_id: int) -> None:
    """EventSub webhook 與 Chat 使用不同的 loop，暫停狀態由 Chat loop 更新。"""
    received_at = _now()
    loop = _loop
    if loop is None or not loop.is_running() or loop is asyncio.get_running_loop():
        await _start_raid_pause(twitch_id, received_at)
        return
    pending = asyncio.run_coroutine_threadsafe(_start_raid_pause(twitch_id, received_at), loop)
    await asyncio.wrap_future(pending)


def _write_log(entry: TwitchEnforcementLog) -> None:
    try:
        twitch_moderation.record_enforcement(entry)
    finally:
        sqldb.release_session()


@dataclass(frozen=True, slots=True)
class _Violation:
    rule: FilterConfig
    strike: int
    stage: Stage

    @property
    def severity(self) -> tuple[int, int]:
        match self.stage["action"]:
            case "ban":
                return 2, 0
            case "timeout":
                return 1, self.stage["duration"] or 0
            case _:
                return 0, 0


def _select_violation(
    msg: ChatMessage, config: ModerationConfig, runtime: _Channel, level: int, user_id: int, now: float
) -> _Violation | None:
    settings = config["settings"]
    strike_window = settings["strike_reset_minutes"] * 60
    runtime.prune(now, strike_window)
    best = None
    for rule in config["filters"]:
        kind, params = rule["kind"], rule["params"]
        if kind == "duplicate":
            if rule["enabled"]:
                runtime.recent_messages.expire(now - params["window_seconds"])
            else:
                runtime.recent_messages.clear()
        if not rule["enabled"] or level >= PERMISSION_LEVELS[rule["exempt_level"]]:
            continue
        if now < runtime.pause_until and kind in _RAID_PAUSED_FILTERS:
            continue
        if kind == "link" and now < runtime.permits.get(user_id, now):
            continue

        occurrences = runtime.recent_messages.add(now, user_id, msg.text) if kind == "duplicate" else 0
        twitch_count = sum(len(positions) for positions in (msg.emotes or {}).values()) if kind == "emote" else 0
        if not twitch_moderation.detect_message(kind, params, msg.text, twitch_count, occurrences):
            continue

        count, last = runtime.strikes.get((user_id, kind), (0, now))
        strike = count + 1 if now - last <= strike_window else 1
        stages = rule["stages"] if rule["stages"] is not None else settings["stages"]
        candidate = _Violation(rule, strike, stages[min(strike, len(stages)) - 1])
        # get_config returns filters in FILTER_KINDS order; a tie keeps the first.
        if best is None or candidate.severity > best.severity:
            best = candidate
    return best


async def check(msg: ChatMessage) -> bool:
    """成功處罰時阻止這則訊息觸發自訂指令。"""
    room_id = msg.room.room_id
    if msg.source_room_id is not None and msg.source_room_id != room_id:
        return False
    twitch_id = int(room_id)
    user = msg.user
    if not _enabled(twitch_id) or user.id == state.bot_user_id:
        return False
    level = viewer_level(msg)
    if level >= PERMISSION_LEVELS["mod"]:
        return False

    user_id = int(user.id)
    runtime = _channels.get(twitch_id)
    if runtime is None:
        runtime = _channels[twitch_id] = _Channel()
    lock = runtime.enforcement_locks.get(user_id)
    if lock is None:
        lock = runtime.enforcement_locks[user_id] = asyncio.Lock()
    async with lock:
        if _channels.get(twitch_id) is not runtime:
            return False
        config = await _config(twitch_id, runtime)
        if _channels.get(twitch_id) is not runtime:
            return False
        violation = _select_violation(msg, config, runtime, level, user_id, _now())
        if violation is None:
            return False

        rule, strike, stage = violation.rule, violation.strike, violation.stage
        kind = rule["kind"]
        action = stage["action"]
        duration = stage["duration"] if action == "timeout" else None
        label = twitch_moderation.FILTER_LABELS[kind]
        try:
            if action == "delete":
                if not msg.id:
                    # twitchAPI 省略 message_id 時會清空整個聊天室。
                    raise ValueError("缺少要刪除的訊息 ID")
                await state.twitch.delete_chat_message(str(twitch_id), state.bot_user_id, msg.id)
            else:
                await state.twitch.ban_user(
                    str(twitch_id), state.bot_user_id, user.id, f"違反{label}過濾規則", duration=duration
                )
        except TwitchAPIException, ClientError, TimeoutError, ValueError:
            log.warning("頻道 %s 的 %s 執法失敗", twitch_id, kind, exc_info=True)
            succeeded = False
        else:
            runtime.strikes[(user_id, kind)] = (strike, _now())
            succeeded = True

        user_name = user.display_name or user.name
        entry = TwitchEnforcementLog(
            twitch_id=twitch_id,
            user_id=user_id,
            user_login=user.name,
            user_name=user_name,
            filter=kind,
            strike=strike,
            action=action,
            duration=duration,
            message=msg.text,
            status="ok" if succeeded else "failed",
        )
        try:
            await asyncio.to_thread(_write_log, entry)
        except SQLAlchemyError:
            log.exception("頻道 %s 的 %s 執法紀錄寫入失敗", twitch_id, kind)
        if succeeded and not rule["silent"] and _channels.get(twitch_id) is runtime:
            now = _now()
            last_notice = runtime.notices.get(kind)
            if last_notice is None or now - last_notice >= twitch_moderation.NOTICE_SECONDS:
                runtime.notices[kind] = now
                default_notice = (
                    twitch_moderation.DEFAULT_NOTICE if kind == "link" else twitch_moderation.GENERAL_NOTICE
                )
                notice = substitute(rule["notice"] or default_notice, {"user": user_name, "filter": label})
                try:
                    await state.chat.send_message(msg.room.name, notice)
                except ClientError, TimeoutError, ValueError:
                    log.warning("頻道 %s 的 %s 執法告知發送失敗", twitch_id, kind, exc_info=True)
        return succeeded


async def permit(cmd: ChatCommand) -> None:
    from starServer.twitch_bot.commands import may_manage

    if not await may_manage(cmd, "放行連結", reply_viewer=True) or cmd.room is None:
        return
    arguments = cmd.parameter.split()
    if len(arguments) != 1 or arguments[0] == "@":
        await cmd.reply("用法：!permit <使用者>")
        return
    twitch_id = int(cmd.room.room_id)
    runtime = _channels.get(twitch_id)
    if runtime is None:
        runtime = _channels[twitch_id] = _Channel()
    login = arguments[0].removeprefix("@").lower()
    try:
        user = await first(state.twitch.get_users(logins=[login]))
    except TwitchAPIException, ClientError, TimeoutError:
        log.warning("查詢 Twitch 帳號失敗", exc_info=True)
        await cmd.reply("目前無法查詢 Twitch 帳號，請稍後再試")
        return
    if user is None:
        await cmd.reply(f"找不到 Twitch 帳號 {login}")
        return
    config = await _config(twitch_id, runtime)
    if _channels.get(twitch_id) is not runtime:
        await cmd.reply("星羽目前未啟用，無法放行連結")
        return
    seconds = config["settings"]["permit_seconds"]
    runtime.permits[int(user.id)] = _now() + seconds
    await cmd.reply(f"已放行 {user.display_name}，{seconds} 秒內可以分享連結")


async def lift(payload: dict[str, Any]) -> dict[str, str]:
    """RPC `moderation.lift`：解除觀眾在頻道的 timeout 或 ban。Twitch 回 400 是不在處罰中、403 是 bot 不是 mod，其他失敗拋錯。"""
    try:
        await state.twitch.unban_user(str(int(payload["twitch_id"])), state.bot_user_id, str(int(payload["user_id"])))
    except TwitchStatusError as exc:
        match exc.status:
            case 400:
                return {"result": "not_punished"}
            case 403:
                return {"result": "not_mod"}
        raise
    return {"result": "lifted"}


async def clear_strikes(payload: dict[str, Any]) -> dict[str, Any]:
    """RPC `moderation.clear_strikes`：清除觀眾在頻道所有過濾器的犯規次數。"""
    runtime = _channels.get(int(payload["twitch_id"]))
    if runtime is not None:
        user_id = int(payload["user_id"])
        runtime.strikes = {key: value for key, value in runtime.strikes.items() if key[0] != user_id}
    return {}
