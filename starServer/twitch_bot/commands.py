"""聊天室指令：!add_cmd、!remove_cmd、!list_cmd 與自訂指令的回應。"""

import functools
import logging
import time
from collections.abc import Callable, Coroutine
from typing import Any

from twitchAPI.chat import ChatCommand, ChatMessage

from starlib.database import sqldb
from starServer.twitch_bot import state, timers

log = logging.getLogger(__name__)


def start() -> None:
    """Twitch bot 初始化完成後呼叫一次；需要註冊快取失效 handler 等啟動工作的功能在這裡做。"""


def stop() -> None:
    """Twitch bot 收尾時呼叫。"""


# this will be called whenever a message in a channel was send by either the bot OR another user
async def on_message(msg: ChatMessage):
    log.info("in %s, %s said: %s", msg.room.name, msg.user.name, msg.text)
    await timers.on_chat_message(int(msg.room.room_id), msg.user.name.lower() == state.chat.username.lower())
    await respond_to_chat_command(msg)


def _can_manage_commands(cmd: ChatCommand) -> bool:
    """只有實況主與該頻道的 mod 能新增、移除自訂指令。"""
    return cmd.user.mod or cmd.user.name == cmd.room.name


def _releases_session[**P](func: Callable[P, Coroutine[Any, Any, None]]) -> Callable[P, Coroutine[Any, Any, None]]:
    """指令跑完釋放 session，讀取開的交易才不會一直握著表的鎖。"""

    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> None:
        try:
            await func(*args, **kwargs)
        finally:
            sqldb.release_session()

    return wrapper


@_releases_session
async def add_chat_command(cmd: ChatCommand):
    if not _can_manage_commands(cmd):
        return
    parameters = cmd.parameter.split(maxsplit=1)
    if len(parameters) < 2:
        await cmd.reply("用法：!add_command <指令> <回覆>")
    else:
        name = parameters[0].removeprefix("!").lower()
        if name in BUILTIN_COMMANDS:
            await cmd.reply(f"{name} 是內建指令，無法覆蓋")
            return
        sqldb.add_twitch_cmd(cmd.room.room_id, name, parameters[1])
        await cmd.reply(f"已新增指令：{name}")


@_releases_session
async def remove_chat_command(cmd: ChatCommand):
    if not _can_manage_commands(cmd):
        return
    name = cmd.parameter.strip().removeprefix("!").lower()
    if not name:
        await cmd.reply("用法：!remove_command <指令>")
    else:
        sqldb.remove_twitch_cmd(cmd.room.room_id, name)
        await cmd.reply(f"已移除指令：{name}")


@_releases_session
async def list_chat_command(cmd: ChatCommand):
    parameters = cmd.parameter
    if len(parameters) < 1:
        commands = sqldb.list_chat_command_by_channel(cmd.room.room_id)
        if commands:
            await cmd.reply(f"指令列表：\n{', '.join([i.name for i in commands])}")
        else:
            await cmd.reply("目前沒有設定指令")
    else:
        command = sqldb.get_chat_command(parameters, cmd.room.room_id)
        if command:
            await cmd.reply(f"{command.name}：{command.response}")
        else:
            await cmd.reply(f"{parameters} 不存在")


# 內建指令由 chat.register_command 處理，自訂指令不可同名
BUILTIN_COMMANDS = frozenset({"add_cmd", "remove_cmd", "list_cmd"})
CUSTOM_COMMAND_COOLDOWN = 30
# (頻道 ID, 指令名稱) -> 上次回應的 monotonic 時間
_custom_command_last_used: dict[tuple[str, str], float] = {}


async def respond_to_chat_command(msg: ChatMessage):
    """自訂指令依頻道各自查快取，同名指令在不同頻道互不影響；每個頻道的每個指令冷卻 30 秒。"""
    parts = msg.text.removeprefix("!").split(maxsplit=1) if msg.text.startswith("!") else []
    if not parts or parts[0].lower() in BUILTIN_COMMANDS:
        return
    name = parts[0].lower()
    resp = sqldb.get_twitch_cmd_response_cache(msg.room.room_id, name)
    if not resp:
        return
    key = (msg.room.room_id, name)
    now = time.monotonic()
    if now - _custom_command_last_used.get(key, -CUSTOM_COMMAND_COOLDOWN) < CUSTOM_COMMAND_COOLDOWN:
        return
    _custom_command_last_used[key] = now
    log.debug("invoke_chat_command: %s %s", name, resp.response)
    await msg.reply(resp.response)


async def modify_channel_information(cmd: ChatCommand):
    pass
