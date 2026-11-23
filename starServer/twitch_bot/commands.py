"""聊天室指令：!add_cmd、!edit_cmd、!remove_cmd、!list_cmd 與自訂指令的觸發。

自訂指令的規則（權限、冷卻、別名、使用次數）在這裡；名稱驗證與寫入在 `starlib.twitch_commands`，後台共用。
"""

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from twitchAPI.chat import ChatCommand, ChatEvent, ChatMessage, EventData

from starlib import twitch_commands
from starlib.database import TwitchChatCommand, sqldb
from starlib.messaging import cache_invalidation
from starlib.twitch_audit import AuditActor
from starlib.twitch_commands import BUILTIN_COMMANDS, PERMISSIONS, CommandFields, CommandInvalid, CommandMissing
from starlib.twitch_speech_check import check_template
from starServer.twitch_bot import speech, state, timers

log = logging.getLogger(__name__)

#: 權限的層級：觸發者的層級要大於等於指令的權限
_LEVEL = {name: level for level, name in enumerate(PERMISSIONS)}
_MOD = _LEVEL["mod"]
#: 冷卻記錄超過這個數量時，順手清掉已過期的
_PRUNE_AT = 1000

#: 現在的時間（秒，monotonic）；測試可以換掉
_now: Callable[[], float] = time.monotonic
#: (頻道 ID, 指令名稱) -> 上次回應的時間
_global_used: dict[tuple[int, str], float] = {}
#: (頻道 ID, 指令名稱, 使用者 ID) -> 上次回應的時間
_user_used: dict[tuple[int, str, str], float] = {}


def start() -> None:
    """Twitch bot 初始化完成後呼叫一次：註冊自訂指令的快取失效 handler。

    Chat 重啟後 READY 會在新的 loop 上再來一次（handler 沿用），這時要把 handler 改綁到新的 loop。
    """
    _register(state.loop)
    state.chat.register_event(ChatEvent.READY, _on_ready)


def stop() -> None:
    """Twitch bot 收尾時呼叫。"""


async def _on_ready(_: EventData) -> None:
    _register(asyncio.get_running_loop())


def _register(loop: asyncio.AbstractEventLoop) -> None:
    cache_invalidation.on_invalidate("twitch_cmd", _on_invalidated, loop)


def _reload(key: str | None) -> None:
    try:
        if key is None:
            sqldb.cache.twitch_cmd.load(sqldb.get_raw_chat_command_all())
        else:
            twitch_id = int(key)
            sqldb.cache.twitch_cmd.set(twitch_id, sqldb.get_raw_chat_command_channel(twitch_id))
    finally:
        sqldb.release_session()


async def _on_invalidated(key: str | None) -> None:
    """指令改了（後台或聊天室，任何一個實例）：重讀該頻道，key 為 None 時重讀全部。"""
    await asyncio.to_thread(_reload, key)


# this will be called whenever a message in a channel was send by either the bot OR another user
async def on_message(msg: ChatMessage):
    log.info("in %s, %s said: %s", msg.room.name, msg.user.name, msg.text)
    await timers.on_chat_message(int(msg.room.room_id), msg.user.name.lower() == state.chat.username.lower())
    await respond_to_chat_command(msg)


# ── 觸發自訂指令 ──────────────────────────────────────────


def _level(msg: ChatMessage) -> int:
    user = msg.user
    if str(user.id) == str(msg.room.room_id):
        return len(PERMISSIONS) - 1
    if user.mod:
        return _MOD
    if user.vip:
        return _LEVEL["vip"]
    if user.subscriber:
        return _LEVEL["subscriber"]
    return 0


def _cooldown_passed(twitch_id: int, cmd: TwitchChatCommand, user_id: str) -> bool:
    """一般觀眾的冷卻判斷；通過就記下這次的時間。全體與個人冷卻都要過。"""
    now = _now()
    global_key = (twitch_id, cmd.name)
    user_key = (twitch_id, cmd.name, user_id)
    if cmd.global_cooldown and now - _global_used.get(global_key, -cmd.global_cooldown) < cmd.global_cooldown:
        return False
    if cmd.user_cooldown and now - _user_used.get(user_key, -cmd.user_cooldown) < cmd.user_cooldown:
        return False
    if cmd.global_cooldown:
        _global_used[global_key] = now
    if cmd.user_cooldown:
        if len(_user_used) > _PRUNE_AT:
            for key in [k for k, at in _user_used.items() if now - at >= twitch_commands.COOLDOWN_MAX]:
                del _user_used[key]
        _user_used[user_key] = now
    return True


def _bump(twitch_id: int, name: str) -> int | None:
    """使用次數加一並回傳新的次數；指令在這之前被刪除時回 None。"""
    try:
        count = sqldb.increment_twitch_cmd_use_count(twitch_id, name)
        sqldb.commit()
        return count
    finally:
        sqldb.release_session()


async def respond_to_chat_command(msg: ChatMessage):
    """依序檢查開關、權限、冷卻（實況主與 mod 不受冷卻限制），通過後計次並發言；名稱與別名是同一個指令。"""
    parts = msg.text.removeprefix("!").split(maxsplit=1) if msg.text.startswith("!") else []
    if not parts or parts[0].lower() in BUILTIN_COMMANDS:
        return
    twitch_id = int(msg.room.room_id)
    cmd = sqldb.get_twitch_cmd_response_cache(twitch_id, parts[0].lower())
    if cmd is None or not cmd.enabled:
        return
    level = _level(msg)
    if level < _LEVEL.get(cmd.permission, len(PERMISSIONS) - 1):
        return
    if level < _MOD and not _cooldown_passed(twitch_id, cmd, str(msg.user.id)):
        return
    count = await asyncio.to_thread(_bump, twitch_id, cmd.name)
    if count is None:
        return
    ctx = speech.SpeechContext(
        twitch_id=twitch_id,
        channel=msg.room.name,
        user=msg.user.display_name or msg.user.name,
        args=parts[1] if len(parts) > 1 else "",
        count=count,
    )
    await speech.say(
        msg.room.name, twitch_id, cmd.response, ctx, source_kind="command", source_key=cmd.name, reply_to=msg
    )


# ── 聊天室管理指令 ────────────────────────────────────────


def _actor(cmd: ChatCommand) -> AuditActor:
    return AuditActor("twitch", str(cmd.user.id), cmd.user.display_name or cmd.user.name)


async def _db[T](func: Callable[..., T], *args: Any, reload_channel: int | None = None) -> T:
    """DB 工作放到 worker thread（寫入會取 advisory lock 與列鎖，不能卡住 event loop），並在該 thread 釋放 session。

    reload_channel 有值表示這是寫入：成功後先在本機重讀該頻道的指令快取，不等 Pub/Sub 回送，
    Redis 連不上時 bot 也能立刻用到剛改的指令；`twitch_commands` 仍會照常通知其他實例與後台。
    """

    def run() -> T:
        try:
            result = func(*args)
            if reload_channel is not None:
                _reload(str(reload_channel))
            return result
        finally:
            sqldb.release_session()

    return await asyncio.to_thread(run)


async def _automod_problem(twitch_id: int, response: str) -> str | None:
    """回應內容會被頻道 AutoMod 擋下或無法檢查時，回聊天室要顯示的原因；沒問題回 None。"""
    match await check_template(twitch_id, response):
        case "blocked":
            return "回應內容會被頻道的 AutoMod 擋下，沒有儲存"
        case "unavailable":
            return "目前無法檢查 AutoMod，請稍後再試"
    return None


async def may_manage(cmd: ChatCommand, what: str, *, reply_viewer: bool = False) -> bool:
    """判斷實況主或 mod 能否執行聊天室管理操作，並依情況回覆拒絕原因。

    每次從資料庫讀取頻道狀態與 mod 協作開關，讓停用、刪除資料或關閉協作立即生效。
    一般觀眾預設保持靜默，reply_viewer 為 True 時回覆權限不足。
    """
    room = cmd.room
    if room is None:
        return False
    is_broadcaster = str(cmd.user.id) == str(room.room_id)
    if not (is_broadcaster or cmd.user.mod):
        if reply_viewer:
            await cmd.reply(f"權限不足：只有實況主或 mod 能{what}")
        return False
    row = await _db(lambda: sqldb.get_twitch_join_channel(int(room.room_id)))
    if row is None or row.state != "enabled":
        await cmd.reply(f"星羽目前未啟用，無法{what}")
        return False
    if not is_broadcaster and not row.mod_collab_enabled:
        await cmd.reply(f"權限不足：實況主已關閉 mod 協作，只有實況主能{what}")
        return False
    return True


async def add_chat_command(cmd: ChatCommand):
    if not await may_manage(cmd, "修改指令"):
        return
    parameters = cmd.parameter.split(maxsplit=1)
    if len(parameters) < 2:
        await cmd.reply("用法：!add_cmd <指令> <回覆>")
        return
    name, response = parameters
    twitch_id = int(cmd.room.room_id)
    fields = CommandFields(response)
    try:
        await _db(twitch_commands.validate, twitch_id, name, fields)
        if problem := await _automod_problem(twitch_id, response):
            await cmd.reply(problem)
            return
        await _db(twitch_commands.create, twitch_id, _actor(cmd), "chat", name, fields, reload_channel=twitch_id)
    except CommandInvalid as e:
        await cmd.reply(e.reason)
        return
    # 不讀回傳的 ORM 物件：它屬於已釋放的 worker thread session，commit 後已過期
    await cmd.reply(f"已新增指令：{twitch_commands.normalize_name(name)}")


async def edit_chat_command(cmd: ChatCommand):
    """!edit_cmd <名稱或別名> <新回應>：只改回應，別名、冷卻、權限、開關與使用次數不動。"""
    if not await may_manage(cmd, "修改指令"):
        return
    parameters = cmd.parameter.split(maxsplit=1)
    if len(parameters) < 2:
        await cmd.reply("用法：!edit_cmd <指令> <新回覆>")
        return
    target, response = parameters
    target = twitch_commands.normalize_name(target)
    twitch_id = int(cmd.room.room_id)
    if target in BUILTIN_COMMANDS:
        await cmd.reply(f"{target} 是內建指令，無法修改")
        return
    row = await _db(twitch_commands.find, twitch_id, target)
    if row is None:
        await cmd.reply(f"{target} 不存在")
        return
    expected = twitch_commands.comparable(twitch_commands.snapshot(row))
    fields = CommandFields(
        response, tuple(row.aliases), row.enabled, row.global_cooldown, row.user_cooldown, row.permission
    )

    def verify(current: dict[str, str | None] | None) -> None:
        # 讀到寫入之間後台改過這個指令：不蓋掉別人的修改
        if current is not None and current != expected:
            raise CommandInvalid("response", "指令剛被修改過，請再試一次")

    try:
        await _db(lambda: twitch_commands.validate(twitch_id, row.name, fields, current_name=row.name))
        if problem := await _automod_problem(twitch_id, response):
            await cmd.reply(problem)
            return
        await _db(
            lambda: twitch_commands.update(twitch_id, _actor(cmd), "chat", row.name, row.name, fields, verify),
            reload_channel=twitch_id,
        )
    except CommandInvalid as e:
        await cmd.reply(e.reason)
        return
    except CommandMissing:
        await cmd.reply(f"{target} 不存在")
        return
    await cmd.reply(f"已修改指令：{row.name}")


async def remove_chat_command(cmd: ChatCommand):
    if not await may_manage(cmd, "修改指令"):
        return
    name = twitch_commands.normalize_name(cmd.parameter)
    if not name:
        await cmd.reply("用法：!remove_cmd <指令或別名>")
        return
    try:
        twitch_id = int(cmd.room.room_id)
        removed = await _db(twitch_commands.remove, twitch_id, _actor(cmd), "chat", name, reload_channel=twitch_id)
    except CommandMissing:
        await cmd.reply(f"{name} 不存在")
        return
    if removed.kind == "alias":
        await cmd.reply(f"已移除別名：{name}（指令 {removed.name} 保留）")
    else:
        await cmd.reply(f"已移除指令：{name}")


async def list_chat_command(cmd: ChatCommand):
    twitch_id = int(cmd.room.room_id)
    parameters = twitch_commands.normalize_name(cmd.parameter)
    if not parameters:
        names = [c.name for c in await _db(twitch_commands.list_commands, twitch_id) if c.enabled]
        if names:
            await cmd.reply(f"指令列表：\n{', '.join(names)}")
        else:
            await cmd.reply("目前沒有設定指令")
    else:
        command = await _db(twitch_commands.find, twitch_id, parameters)
        if command is not None and command.enabled:
            await cmd.reply(f"{command.name}：{command.response}")
        else:
            await cmd.reply(f"{parameters} 不存在")


async def modify_channel_information(cmd: ChatCommand):
    pass
