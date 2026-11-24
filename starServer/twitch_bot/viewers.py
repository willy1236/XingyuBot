"""觀眾層級、常客快取與聊天室的常客管理指令。"""

import asyncio
import logging
import threading

from aiohttp import ClientError
from twitchAPI.chat import ChatCommand, ChatMessage, EventData
from twitchAPI.helper import first
from twitchAPI.object.api import TwitchUser
from twitchAPI.type import TwitchAPIException

from starlib import twitch_regulars
from starlib.database import sqldb
from starlib.messaging import cache_invalidation
from starlib.twitch_audit import AuditActor
from starlib.twitch_commands import PERMISSIONS
from starServer.twitch_bot import state

log = logging.getLogger(__name__)

PERMISSION_LEVELS = {name: level for level, name in enumerate(PERMISSIONS)}
_regular_ids: dict[int, set[int]] = {}
# Redis 失效通知和聊天室操作都可能重讀。把讀取及發布排在一起，才不會用舊的全量結果覆蓋新的單頻道結果。
_reload_lock = threading.Lock()


def _reload(twitch_id: int | None = None) -> None:
    global _regular_ids
    with _reload_lock:
        try:
            rows = twitch_regulars.list_regulars(twitch_id)
            if twitch_id is None:
                by_channel: dict[int, set[int]] = {}
                for row in rows:
                    by_channel.setdefault(row.twitch_id, set()).add(row.user_id)
                _regular_ids = by_channel
            elif rows:
                _regular_ids[twitch_id] = {row.user_id for row in rows}
            else:
                _regular_ids.pop(twitch_id, None)
        finally:
            sqldb.release_session()


async def load_regulars() -> None:
    """開始接收聊天室訊息前載入全部頻道。"""
    await asyncio.to_thread(_reload)


async def on_ready(_: EventData) -> None:
    cache_invalidation.on_invalidate("twitch_regular", _on_invalidated, asyncio.get_running_loop())
    # 補讀 Chat 尚未綁定失效 handler 期間的變更，包含 Chat 重啟。
    await load_regulars()


async def _on_invalidated(key: str | None) -> None:
    await asyncio.to_thread(_reload, int(key) if key is not None else None)


def viewer_level(msg: ChatMessage) -> int:
    twitch_id = int(msg.room.room_id)
    user = msg.user
    user_id = int(user.id)
    if user_id == twitch_id:
        return len(PERMISSIONS) - 1
    if user.mod:
        return PERMISSION_LEVELS["mod"]
    if user.vip:
        return PERMISSION_LEVELS["vip"]
    regular_ids = _regular_ids.get(twitch_id)
    if regular_ids is not None and user_id in regular_ids:
        return PERMISSION_LEVELS["regular"]
    if user.subscriber:
        return PERMISSION_LEVELS["subscriber"]
    return PERMISSION_LEVELS["everyone"]


def _change_regular(twitch_id: int, actor: AuditActor, user: TwitchUser, *, add: bool) -> bool:
    try:
        if add:
            changed = twitch_regulars.add(twitch_id, actor, "chat", int(user.id), user.login, user.display_name)
        else:
            changed = twitch_regulars.remove(twitch_id, actor, "chat", int(user.id))
    finally:
        sqldb.release_session()
    if changed:
        _reload(twitch_id)
    return changed


async def regular_command(cmd: ChatCommand) -> None:
    from starServer.twitch_bot.commands import may_manage

    if not await may_manage(cmd, "管理常客"):
        return
    parts = cmd.parameter.split()
    if len(parts) != 2 or parts[0] not in {"add", "remove"} or parts[1] == "@":
        await cmd.reply("用法：!regular add|remove <使用者>")
        return
    action, login = parts
    login = login.removeprefix("@").lower()
    try:
        user = await first(state.twitch.get_users(logins=[login])) if twitch_regulars.valid_login(login) else None
    except TwitchAPIException, ClientError, TimeoutError:
        log.warning("查詢 Twitch 帳號失敗", exc_info=True)
        await cmd.reply("目前無法查詢 Twitch 帳號，請稍後再試")
        return
    if user is None:
        await cmd.reply(f"找不到 Twitch 帳號 {login}")
        return

    actor = AuditActor("twitch", str(cmd.user.id), cmd.user.display_name or cmd.user.name)
    adding = action == "add"
    changed = await asyncio.to_thread(_change_regular, int(cmd.room.room_id), actor, user, add=adding)
    if adding:
        reply = f"已將 {user.display_name} 加入常客" if changed else f"{user.display_name} 已經是常客"
    else:
        reply = f"已將 {user.display_name} 移出常客" if changed else f"{user.display_name} 不是常客"
    await cmd.reply(reply)
