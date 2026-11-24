"""聊天室過濾、執法與暫時放行。執行期狀態只由 Chat loop 存取。"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from weakref import WeakValueDictionary

from aiohttp import ClientError
from sqlalchemy.exc import SQLAlchemyError
from twitchAPI.chat import ChatCommand, ChatMessage, EventData
from twitchAPI.helper import first
from twitchAPI.type import TwitchAPIException

from starlib import twitch_moderation
from starlib.database import TwitchEnforcementLog, sqldb
from starlib.messaging import cache_invalidation
from starlib.twitch_moderation import ModerationConfig
from starlib.twitch_speech_check import substitute
from starServer.twitch_bot import state
from starServer.twitch_bot.viewers import PERMISSION_LEVELS, viewer_level

log = logging.getLogger(__name__)
_now: Callable[[], float] = time.monotonic


@dataclass(slots=True)
class _Channel:
    config: ModerationConfig | None = None
    config_generation: int = 0
    config_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    enforcement_locks: WeakValueDictionary[tuple[int, str], asyncio.Lock] = field(default_factory=WeakValueDictionary)
    strikes: dict[tuple[int, str], tuple[int, float]] = field(default_factory=dict)
    permits: dict[int, float] = field(default_factory=dict)
    notices: dict[str, float] = field(default_factory=dict)
    next_prune: float = 0.0

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


async def on_ready(_: EventData) -> None:
    global _loop
    loop = asyncio.get_running_loop()
    if _loop is not loop:
        for runtime in _channels.values():
            runtime.config_lock = asyncio.Lock()
            runtime.enforcement_locks.clear()
        _loop = loop
    cache_invalidation.on_invalidate("twitch_moderation", _on_invalidated, loop)
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


def _write_log(entry: TwitchEnforcementLog) -> None:
    try:
        twitch_moderation.record_enforcement(entry)
    finally:
        sqldb.release_session()


async def check(msg: ChatMessage) -> bool:
    """成功處罰時阻止這則訊息觸發自訂指令。"""
    twitch_id = int(msg.room.room_id)
    user = msg.user
    if not _enabled(twitch_id) or user.id == state.bot_user_id:
        return False
    level = viewer_level(msg)
    if level >= PERMISSION_LEVELS["mod"]:
        return False

    kind = "link"
    user_id = int(user.id)
    runtime = _channels.get(twitch_id)
    if runtime is None:
        runtime = _channels[twitch_id] = _Channel()
    key = (user_id, kind)
    lock = runtime.enforcement_locks.get(key)
    if lock is None:
        lock = runtime.enforcement_locks[key] = asyncio.Lock()
    async with lock:
        if _channels.get(twitch_id) is not runtime:
            return False
        config = await _config(twitch_id, runtime)
        if _channels.get(twitch_id) is not runtime:
            return False
        link = next(item for item in config["filters"] if item["kind"] == kind)
        if not link["enabled"] or level >= PERMISSION_LEVELS[link["exempt_level"]]:
            return False

        now = _now()
        settings = config["settings"]
        strike_window = settings["strike_reset_minutes"] * 60
        runtime.prune(now, strike_window)
        if now < runtime.permits.get(user_id, now) or not twitch_moderation.detect_link(
            msg.text, link["params"]["whitelist"]
        ):
            return False

        count, last = runtime.strikes.get(key, (0, now))
        strike = count + 1 if now - last <= strike_window else 1
        stages = link["stages"] if link["stages"] is not None else settings["stages"]
        stage = stages[min(strike, len(stages)) - 1]
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
            runtime.strikes[key] = (strike, _now())
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
        if succeeded and not link["silent"] and _channels.get(twitch_id) is runtime:
            now = _now()
            last_notice = runtime.notices.get(kind)
            if last_notice is None or now - last_notice >= twitch_moderation.NOTICE_SECONDS:
                runtime.notices[kind] = now
                notice = substitute(
                    link["notice"] or twitch_moderation.DEFAULT_NOTICE, {"user": user_name, "filter": label}
                )
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
