"""私人頻道的鎖定、重開與刪除（網頁後台與頻道內按鈕共用），以及 bot 啟動時載入與更新頻道的操作按鈕。

依賴 `TicketChannelView`，所以放在 starDiscord；覆寫怎麼算、誰能按什麼在 `starlib/tickets.py`。
全部讀寫 Discord 物件，必須在 bot 的事件迴圈上呼叫。錯誤一律丟 `TicketActionError`，由呼叫端轉成自己的回應。

同一個私人頻道的鎖定、重開、刪除以「每頻道一把鎖」序列化；另外持有所屬大廳的 `lobby_lock`，
與大廳修改時套用管理身分組（同樣會改這個頻道的覆寫與 `locked_overwrites_json`）互斥。
取鎖順序固定為「頻道 → 大廳」，大廳那邊的流程不取頻道鎖，不會互等。
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

import discord

from starlib import sqldb
from starlib.tickets import (
    TicketAction,
    allowed_ticket_actions,
    locked_overwrites,
    parse_locked_overwrites,
    raw_overwrites,
    reopened_overwrites,
)
from starlib.utils import nowtz

from .ticket_lobby import lobby_lock
from .uiElement.view import TicketChannelView

log = logging.getLogger(__name__)

TicketActionErrorCode = Literal[
    "not_found", "channel_gone", "forbidden", "bot_missing_permission", "discord_error", "save_failed", "failed"
]


class TicketActionError(Exception):
    """`code`：
    - not_found：沒有這個私人頻道的紀錄（或不屬於這個伺服器）。
    - channel_gone：頻道已在 Discord 被刪除，紀錄已一併移除。
    - bot_missing_permission：bot 缺 Manage Roles／Manage Channels，Discord 拒絕。
    - discord_error：其他 Discord 錯誤，`message` 是 Discord 回的說明。
    - forbidden：按鈕的操作者在取得鎖之後重新檢查，已沒有這個動作的權限（例如等鎖期間大廳被移除）。
    - save_failed：資料庫寫入失敗，Discord 上的變更已還原。
    - failed：其他非預期的錯誤（例如讀資料庫失敗），已記 log。
    """

    def __init__(self, code: TicketActionErrorCode, message: str | None = None):
        super().__init__(code, message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class TicketState:
    channel_id: int
    status: Literal["open", "locked", "deleted"]
    #: False 表示目標本來就是要求的狀態，什麼都沒做
    changed: bool


def _db[T](fn: Callable[[], T]) -> T:
    """bot 事件迴圈上的 DB 存取；做完釋放 session，不佔住連線。"""
    try:
        return fn()
    finally:
        sqldb.release_session()


_locks: dict[int, asyncio.Lock] = {}


def ticket_lock(channel_id: int) -> asyncio.Lock:
    """每個私人頻道一把鎖（bot 是單一 process）。"""
    return _locks.setdefault(channel_id, asyncio.Lock())


async def _run_locked[T](channel_id: int, fn: Callable[[], Awaitable[T]]) -> T:
    """持有頻道鎖與所屬大廳的鎖執行 `fn`。

    等大廳鎖的期間頻道可能被搬到別的大廳（大廳換頻道）或改為未歸屬（移除大廳），取到後重讀，歸屬變了就換鎖重來。
    `TicketActionError` 以外的例外記 log 後轉成 `failed`。
    """
    try:
        async with ticket_lock(channel_id):
            while True:
                snap = _db(lambda: sqldb.get_ticket_snapshot(channel_id))
                lobby_id = snap["lobby_channel_id"] if snap is not None else None
                if lobby_id is None:
                    return await fn()
                async with lobby_lock(lobby_id):
                    again = _db(lambda: sqldb.get_ticket_snapshot(channel_id))
                    if again is None or again["lobby_channel_id"] == lobby_id:
                        return await fn()
    except TicketActionError:
        raise
    except Exception:
        # 讀資料庫失敗等非預期錯誤也要轉成呼叫端認得的錯誤，按鈕才不會停在「思考中」
        log.exception("Ticket: action failed", extra={"channel_id": channel_id})
        raise TicketActionError("failed") from None


def _manager_role_ids(snap: dict) -> list[int]:
    """所屬大廳現行的管理身分組；未歸屬或大廳已移除回空的。"""
    lobby_id = snap["lobby_channel_id"]
    if lobby_id is None:
        return []
    lobby = _db(lambda: sqldb.get_ticket_lobby_snapshot(lobby_id))
    if lobby is None or lobby["removed_at"] is not None:
        return []
    return lobby["manager_role_ids"]


def _http_error(e: discord.HTTPException) -> TicketActionError:
    if isinstance(e, discord.Forbidden):
        return TicketActionError("bot_missing_permission")
    return TicketActionError("discord_error", e.text or str(e))


def _load(guild: discord.Guild, channel_id: int) -> tuple[dict, discord.abc.GuildChannel | None]:
    """讀紀錄與頻道；紀錄不存在或不屬於這個伺服器丟 not_found。頻道已不在時刪紀錄，回傳的頻道為 None。

    呼叫端須先確認伺服器不是 unavailable，頻道不在快取才代表真的被刪。
    """
    snap = _db(lambda: sqldb.get_ticket_snapshot(channel_id))
    if snap is None or snap["guild_id"] != guild.id:
        raise TicketActionError("not_found")
    channel = guild.get_channel(channel_id)
    if channel is None:
        _db(lambda: sqldb.delete_ticket_channels([channel_id]))
    return snap, channel


async def _fetch_fresh(guild: discord.Guild, channel_id: int) -> discord.abc.GuildChannel:
    """向 Discord 讀頻道目前的覆寫，計算與還原都用這份。

    不用快取：py-cord 的覆寫快取要等 gateway 的 CHANNEL_UPDATE 才更新（`set_permissions`、`edit` 都不改本地快取），
    剛釋放大廳鎖的 P-02 套用管理身分組、或剛做完的重開，快取可能還是舊的，整批 `edit(overwrites=)` 會把那些變更蓋掉。
    頻道已不在時刪紀錄並丟 channel_gone。
    """
    try:
        return await guild.fetch_channel(channel_id)  # pyright: ignore[reportReturnType]
    except discord.NotFound:
        _db(lambda: sqldb.delete_ticket_channels([channel_id]))
        raise TicketActionError("channel_gone") from None
    except discord.HTTPException as e:
        raise _http_error(e) from None


def _check_member(guild: discord.Guild, channel_id: int, member: discord.Member | None, action: TicketAction) -> None:
    """按鈕的操作者在鎖內重新檢查權限（等鎖期間大廳可能被移除、管理身分組可能被改）；後台傳 None 不檢查。"""
    if member is not None and action not in member_ticket_actions(guild, channel_id, member):
        raise TicketActionError("forbidden")


async def _set_control_message(channel: discord.abc.GuildChannel, message_id: int | None, locked: bool) -> None:
    """把置頂的操作訊息換成對應狀態的按鈕；訊息不在或改不了只記 log（之後只能從後台操作）。"""
    if message_id is None:
        return
    view = TicketChannelView(channel.id, locked)
    try:
        message = channel.get_partial_message(message_id)  # pyright: ignore[reportAttributeAccessIssue]
        await message.edit(view=view)
    except discord.HTTPException:
        # py-cord 的 edit 成功時已登記這個 view（store_view），不必再 add_view
        log.warning("Ticket: failed to update the control message", extra={"channel_id": channel.id})


async def _notify(channel: discord.abc.GuildChannel, text: str) -> None:
    try:
        await channel.send(text, allowed_mentions=discord.AllowedMentions.none())  # pyright: ignore[reportAttributeAccessIssue]
    except discord.HTTPException:
        log.warning("Ticket: failed to send the notice", extra={"channel_id": channel.id})


async def _apply(channel: discord.abc.GuildChannel, overwrites: dict, reason: str) -> dict:
    """整批套用覆寫，回傳套用前的覆寫（還原用）。"""
    before = {target: overwrite for _, target, overwrite in raw_overwrites(channel)}
    try:
        await channel.edit(overwrites=overwrites, reason=reason)
    except discord.HTTPException as e:
        raise _http_error(e) from None
    return before


async def _restore(channel: discord.abc.GuildChannel, before: dict, reason: str) -> None:
    try:
        await channel.edit(overwrites=before, reason=reason)
    except discord.HTTPException:
        log.exception("Ticket: failed to restore overwrites", extra={"channel_id": channel.id})


async def lock_ticket(
    guild: discord.Guild, channel_id: int, actor: discord.Member, reason: str, *, check_member: bool = False
) -> TicketState:
    """鎖定：bot 以外所有覆寫對象都不能發言，鎖定前的 `send_messages` 存進 `locked_overwrites_json`。

    已鎖定時什麼都不做（`changed=False`）。資料庫寫入失敗時還原覆寫。操作訊息換成重開與刪除按鈕，頻道內公告鎖定者。
    `check_member`：按鈕呼叫時為 True，在鎖內重新檢查 `actor` 的權限。

    Raises:
        TicketActionError: 見 `TicketActionErrorCode`。
    """

    async def run() -> TicketState:
        snap, channel = _load(guild, channel_id)
        if channel is None:
            raise TicketActionError("channel_gone")
        _check_member(guild, channel_id, actor if check_member else None, "lock")
        if snap["closed_at"] is not None:
            return TicketState(channel_id, "locked", False)
        channel = await _fetch_fresh(guild, channel_id)
        overwrites, saved = locked_overwrites(channel, guild.me)
        before = await _apply(channel, overwrites, reason)
        try:
            ok = _db(lambda: sqldb.lock_ticket_record(channel_id, actor.id, nowtz(), json.dumps(saved)))
        except Exception:
            log.exception("Ticket: DB write failed on lock", extra={"channel_id": channel_id})
            ok = None
        if not ok:
            await _restore(channel, before, reason)
            raise TicketActionError("save_failed")
        await _set_control_message(channel, snap["view_message_id"], locked=True)
        await _notify(channel, f"頻道已由 {actor.mention} 鎖定")
        return TicketState(channel_id, "locked", True)

    return await _run_locked(channel_id, run)


async def reopen_ticket(
    guild: discord.Guild, channel_id: int, actor: discord.Member, reason: str, *, check_member: bool = False
) -> TicketState:
    """重開：恢復鎖定前的發言權限後清空保存值；沒有保存值（測試版鎖定）時照預設規則恢復，見 `reopened_overwrites`。

    未鎖定時什麼都不做（`changed=False`）。資料庫寫入失敗時還原覆寫。操作訊息換回鎖定按鈕，頻道內公告重開者。
    `check_member`：按鈕呼叫時為 True，在鎖內重新檢查 `actor` 的權限。

    Raises:
        TicketActionError: 見 `TicketActionErrorCode`。
    """

    async def run() -> TicketState:
        snap, channel = _load(guild, channel_id)
        if channel is None:
            raise TicketActionError("channel_gone")
        _check_member(guild, channel_id, actor if check_member else None, "reopen")
        if snap["closed_at"] is None:
            return TicketState(channel_id, "open", False)
        channel = await _fetch_fresh(guild, channel_id)
        overwrites = reopened_overwrites(
            channel,
            guild.me,
            parse_locked_overwrites(snap["locked_overwrites_json"]),
            creator_id=snap["creator_id"],
            manager_role_ids=_manager_role_ids(snap),
        )
        before = await _apply(channel, overwrites, reason)
        try:
            ok = _db(lambda: sqldb.reopen_ticket_record(channel_id))
        except Exception:
            log.exception("Ticket: DB write failed on reopen", extra={"channel_id": channel_id})
            ok = None
        if not ok:
            await _restore(channel, before, reason)
            raise TicketActionError("save_failed")
        await _set_control_message(channel, snap["view_message_id"], locked=False)
        await _notify(channel, f"頻道已由 {actor.mention} 重新開啟")
        return TicketState(channel_id, "open", True)

    return await _run_locked(channel_id, run)


async def delete_ticket(
    guild: discord.Guild, channel_id: int, reason: str, *, member: discord.Member | None = None
) -> TicketState:
    """刪除 Discord 頻道與紀錄（對話無法復原）。

    沒有紀錄或頻道已不在時視為已刪除（`changed=False`）；沒有紀錄時不動 Discord，不會刪到不是私人頻道的頻道。
    頻道刪除後紀錄刪除失敗只記 log，下次載入清單時會清掉。
    `member`：按鈕呼叫時傳操作者，在鎖內重新檢查權限；後台傳 None。

    Raises:
        TicketActionError: bot_missing_permission、discord_error。
    """

    async def run() -> TicketState:
        try:
            _, channel = _load(guild, channel_id)
        except TicketActionError:
            return TicketState(channel_id, "deleted", False)
        if channel is None:
            return TicketState(channel_id, "deleted", False)
        _check_member(guild, channel_id, member, "delete")
        try:
            await channel.delete(reason=reason)
        except discord.NotFound:
            pass
        except discord.HTTPException as e:
            raise _http_error(e) from None
        try:
            _db(lambda: sqldb.delete_ticket_channels([channel_id]))
        except Exception:
            log.exception("Ticket: DB delete failed", extra={"channel_id": channel_id})
        return TicketState(channel_id, "deleted", True)

    return await _run_locked(channel_id, run)


def member_ticket_actions(guild: discord.Guild, channel_id: int, member: discord.Member) -> set[TicketAction]:
    """成員在 Discord 內能對這個私人頻道按的動作；沒有紀錄時只看 Manage Channels。

    建立者與管理身分組只在頻道屬於還在使用的大廳時算數（未歸屬、大廳已移除時只剩 Manage Channels）。
    """
    manage_channels = bool(member.guild_permissions.manage_channels)
    snap = _db(lambda: sqldb.get_ticket_snapshot(channel_id))
    if snap is None or snap["guild_id"] != guild.id:
        return allowed_ticket_actions(is_creator=False, is_manager=False, manage_channels=manage_channels)
    managers = _manager_role_ids(snap)
    active = snap["lobby_channel_id"] is not None and _lobby_active(snap["lobby_channel_id"])
    role_ids = {r.id for r in member.roles}
    return allowed_ticket_actions(
        is_creator=active and snap["creator_id"] == member.id,
        is_manager=any(rid in role_ids for rid in managers),
        manage_channels=manage_channels,
    )


def _lobby_active(lobby_id: int) -> bool:
    lobby = _db(lambda: sqldb.get_ticket_lobby_snapshot(lobby_id))
    return lobby is not None and lobby["removed_at"] is None


def _custom_ids(message: discord.Message) -> list[str]:
    return [
        child.custom_id
        for row in message.components
        for child in getattr(row, "children", [])
        if getattr(child, "custom_id", None)
    ]


#: 置頂訊息的一次性更新是否已在這個 process 做過；重連時 on_ready 會再觸發，只重新登記 view
_messages_refreshed = False


async def restore_ticket_views(bot: discord.Bot) -> None:
    """bot 啟動時：所有還有紀錄的私人頻道（含已鎖定）依狀態載入操作按鈕。

    第一次 ready 時另外檢查置頂操作訊息：還是舊按鈕（上線前的「關閉頻道」或狀態不符）時換成新按鈕，已是新按鈕就不動；
    之後的 ready（重連）只重新登記 view，不再逐一讀訊息。
    頻道或訊息已不在的略過：頻道紀錄由後台載入時清除，訊息不在的頻道只能從後台操作。單一頻道的錯誤只記 log，不中斷 on_ready。
    """
    global _messages_refreshed
    refresh = not _messages_refreshed
    _messages_refreshed = True
    tickets = _db(
        lambda: [(t.channel_id, t.view_message_id, t.closed_at is not None) for t in sqldb.list_all_ticket_channels()]
    )
    for channel_id, message_id, locked in tickets:
        try:
            channel = bot.get_channel(channel_id)
            if channel is None or message_id is None:
                continue
            view = TicketChannelView(channel_id, locked)
            bot.add_view(view, message_id=message_id)
            if not refresh:
                continue
            message = await channel.fetch_message(message_id)  # pyright: ignore[reportAttributeAccessIssue]
            if _custom_ids(message) != [item.custom_id for item in view.children]:  # pyright: ignore[reportAttributeAccessIssue]
                await message.edit(view=view)
                log.info("Ticket control message updated", extra={"channel_id": channel_id})
        except discord.HTTPException:
            log.warning("Ticket control message unavailable", extra={"channel_id": channel_id})
        except Exception:
            log.exception("Ticket: failed to restore the control view", extra={"channel_id": channel_id})
