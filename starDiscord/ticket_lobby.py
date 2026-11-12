"""私人頻道大廳的建立、更新與移除（網頁後台與 `/ticket setup`（P-05）共用），以及成員從大廳開單。

依賴 `TicketLobbyView`，所以放在 starDiscord；不依賴 view 的規則在 `starlib/tickets.py`。
全部讀寫 Discord 物件，必須在 bot 的事件迴圈上呼叫。錯誤一律丟 `LobbyError`，由呼叫端轉成自己的回應。
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Literal

import discord

from starlib import sclient, sqldb
from starlib.database import TicketChannel
from starlib.message_content import MessageContent, from_json, to_json, to_send_kwargs
from starlib.moderation import audit_reason
from starlib.tickets import (
    ApplyFailure,
    apply_manager_role_changes,
    build_ticket_overwrites,
    default_lobby_content,
    lobby_invalid_reason,
)
from starlib.utils import nowtz

from .uiElement.view import TicketChannelView, TicketLobbyView

log = logging.getLogger(__name__)

LobbyErrorCode = Literal[
    "channel_not_found",
    "category_not_found",
    "channel_in_use",
    "channel_access",
    "lobby_exists",
    "conflict",
    "discord_error",
    "save_failed",
]


class LobbyError(Exception):
    """`code` 說明原因；`message` 是 Discord 回的說明（discord_error 時）。"""

    def __init__(self, code: LobbyErrorCode, message: str | None = None):
        super().__init__(code, message)
        self.code = code
        self.message = message


class LobbyConflict(LobbyError):
    """大廳在呼叫端讀取之後被別人改過，或已被移除（`deleted`）。"""

    def __init__(self, deleted: bool):
        super().__init__("conflict")
        self.deleted = deleted


@dataclass(frozen=True)
class NewChannel:
    """讓 bot 新建大廳頻道。"""

    name: str
    category_id: int


@dataclass(frozen=True)
class LobbyValues:
    #: 大廳頻道：既有頻道的 ID，或 `NewChannel`
    channel: int | NewChannel
    ticket_category_id: int
    manager_role_ids: list[int]
    #: 已正規化的前綴
    name_prefix: str
    one_per_user: bool
    max_open: int | None
    #: None 沿用目前存下的內容，都沒有則用預設內容
    message: MessageContent | None
    button_label: str | None
    button_emoji: str | None
    #: 稽核日誌的 reason
    reason: str
    #: 修改既有大廳時，被修改的大廳頻道 ID；None 表示新增
    previous_channel_id: int | None = None
    #: 修改時的衝突比對：大廳欄位名稱 → 呼叫端讀到的值；None 表示不比對
    original: dict | None = None


@dataclass(frozen=True)
class SaveResult:
    channel_id: int
    message_id: int
    jump_url: str
    #: 套用管理身分組失敗的私人頻道；大廳設定仍已存檔
    failures: list[ApplyFailure] = field(default_factory=list)


@dataclass(frozen=True)
class _Ticket:
    channel_id: int
    closed_at: object
    locked_overwrites_json: str | None


def _db[T](fn) -> T:
    """bot 事件迴圈上的 DB 存取；做完釋放 session，不佔住連線。"""
    try:
        return fn()
    finally:
        sqldb.release_session()


def _http_error(e: discord.HTTPException) -> LobbyError:
    return LobbyError("discord_error", e.text or str(e))


_locks: dict[int, asyncio.Lock] = {}


def lobby_lock(channel_id: int) -> asyncio.Lock:
    """每個大廳一把鎖（bot 是單一 process）：同一個大廳的修改、移除與開單（P-03）互相序列化。

    新增、修改、移除在整個流程（含失敗時的還原）都持有這把鎖，才不會出現「移除完成後，另一個修改把按鈕加回去」
    或「兩個修改交錯，敗方的還原蓋掉勝方的內容」。
    """
    return _locks.setdefault(channel_id, asyncio.Lock())


@asynccontextmanager
async def _locked(*channel_ids: int | None) -> AsyncIterator[None]:
    """依 ID 由小到大取得多個大廳的鎖（換頻道時同時鎖舊的與新的），避免兩邊互等。"""
    locks = [lobby_lock(i) for i in sorted({i for i in channel_ids if i is not None})]
    acquired: list[asyncio.Lock] = []
    try:
        for lock in locks:
            await lock.acquire()
            acquired.append(lock)
        yield
    finally:
        for lock in reversed(acquired):
            lock.release()


async def _delete_quietly(
    target: discord.Message | discord.abc.GuildChannel, what: str, reason: str | None = None
) -> None:
    """還原用的刪除；頻道帶稽核原因（訊息的刪除沒有這個參數）。"""
    try:
        if isinstance(target, discord.Message):
            await target.delete()
        else:
            await target.delete(reason=reason)
    except discord.HTTPException:
        log.exception("Ticket lobby: failed to delete %s", what)


def _bot_avatar(guild: discord.Guild) -> str | None:
    avatar = getattr(guild.me, "display_avatar", None)
    return avatar.url if avatar is not None else None


async def save_lobby(guild: discord.Guild, v: LobbyValues) -> SaveResult:
    """新增或修改大廳，持有該大廳（換頻道時含新頻道）的鎖；說明見 `_save_lobby`。"""
    async with _locked(v.previous_channel_id, v.channel if isinstance(v.channel, int) else None):
        return await _save_lobby(guild, v)


async def _save_lobby(guild: discord.Guild, v: LobbyValues) -> SaveResult:
    """新增或修改大廳：建立（或沿用）大廳頻道、發送或更新大廳訊息、寫資料庫，修改時再把管理身分組的增減套用到底下的私人頻道。

    - 新增：同頻道有已移除的大廳時覆寫它（保留流水號）。
    - 修改：大廳頻道還在時只能改設定；原頻道已被刪除時可改選頻道，底下的私人頻道與流水號跟著搬過去。
    - 大廳訊息被刪時重新發送。
    - 資料庫寫入失敗時，把剛送出或剛編輯的訊息還原，新建的頻道一併刪除。

    Raises:
        LobbyError: 見 `LobbyErrorCode`；`LobbyConflict` 表示大廳已被別人改過或移除。
    """
    prev = v.previous_channel_id
    old = None
    if prev is not None:
        old = _db(lambda: sqldb.get_ticket_lobby_snapshot(prev))
        if old is None or old["removed_at"] is not None or old["guild_id"] != guild.id:
            raise LobbyConflict(deleted=True)

    # 1. 決定大廳頻道（先做不會留下東西的檢查，再建立頻道）
    created: discord.TextChannel | None = None
    if isinstance(v.channel, NewChannel):
        category = guild.get_channel(v.channel.category_id)
        if category is None or category.type != discord.ChannelType.category:
            raise LobbyError("category_not_found")
        if prev is not None and guild.get_channel(prev) is not None:
            raise LobbyError("channel_in_use")
        try:
            created = await guild.create_text_channel(v.channel.name, category=category, reason=v.reason)  # pyright: ignore[reportArgumentType]
        except discord.HTTPException as e:
            raise _http_error(e) from None
        channel = created
    else:
        found = guild.get_channel(v.channel)
        if found is None or found.type != discord.ChannelType.text:
            raise LobbyError("channel_not_found")
        channel = found
        if prev is not None and channel.id != prev and guild.get_channel(prev) is not None:
            raise LobbyError("channel_in_use")
        if channel.id != prev:
            existing = _db(lambda: sqldb.get_ticket_lobby_snapshot(channel.id))
            if existing is not None and existing["removed_at"] is None:
                raise LobbyError("lobby_exists")
    target_id = channel.id

    # 2. 內容與按鈕
    if v.message is not None:
        content = v.message
    elif old is not None and old["content_json"] is not None:
        content = from_json(old["content_json"])
    else:
        content = default_lobby_content(_bot_avatar(guild))
    kwargs = to_send_kwargs(content)
    view = TicketLobbyView(target_id, v.button_label, v.button_emoji)

    # 3. Discord 訊息：原位更新，或發新訊息（新大廳、大廳訊息被刪、換頻道）
    edited: discord.Message | None = None
    restore: dict = {}
    sent: discord.Message | None = None
    try:
        if old is not None and target_id == prev:
            try:
                edited = await channel.fetch_message(old["message_id"])  # pyright: ignore[reportAttributeAccessIssue]
            except discord.NotFound:
                edited = None
            except discord.Forbidden:
                # 缺 Read Message History 或 View Channel：讀不到不代表訊息被刪，不能改發新訊息
                raise LobbyError("channel_access") from None
            if edited is not None:
                restore = {
                    "content": edited.content or None,
                    "embeds": list(edited.embeds),
                    "view": TicketLobbyView(prev, old["button_label"], old["button_emoji"]),
                }
                await edited.edit(**kwargs, view=view)
        if edited is None:
            sent = await channel.send(**kwargs, view=view, allowed_mentions=discord.AllowedMentions.none())  # pyright: ignore[reportAttributeAccessIssue]
    except discord.HTTPException as e:
        if created is not None:
            await _delete_quietly(created, "created channel", v.reason)
        raise _http_error(e) from None
    message = sent or edited
    assert message is not None
    sclient.bot.add_view(view, message_id=message.id)  # pyright: ignore[reportOptionalMemberAccess]

    async def undo() -> None:
        if sent is not None:
            await _delete_quietly(sent, "lobby message")
        elif edited is not None:
            try:
                await edited.edit(**restore)
                sclient.bot.add_view(restore["view"], message_id=edited.id)  # pyright: ignore[reportOptionalMemberAccess]
            except discord.HTTPException:
                log.exception("Ticket lobby: failed to restore message", extra={"message_id": edited.id})
        if created is not None:
            await _delete_quietly(created, "created channel", v.reason)

    # 4. 資料庫
    values = {
        "message_id": message.id,
        "ticket_category_id": v.ticket_category_id,
        "name_prefix": v.name_prefix,
        "one_per_user": v.one_per_user,
        "max_open": v.max_open,
        "content_json": to_json(content),
        "button_label": v.button_label,
        "button_emoji": v.button_emoji,
    }
    own_category = {"category_id": getattr(channel, "category_id", None) or 0}
    try:
        if old is None:
            ok = _db(
                lambda: sqldb.insert_ticket_lobby(
                    {"channel_id": target_id, "guild_id": guild.id, **own_category, **values}, v.manager_role_ids
                )
            )
            failure: LobbyError | None = None if ok else LobbyError("lobby_exists")
        elif target_id == prev:
            ok = _db(lambda: sqldb.update_ticket_lobby_if(prev, v.original or {}, values, v.manager_role_ids))
            failure = None if ok else LobbyConflict(deleted=False)
        else:
            ok = _db(lambda: sqldb.move_ticket_lobby(prev, target_id, {**own_category, **values}, v.manager_role_ids))
            failure = None if ok else LobbyConflict(deleted=False)
    except Exception:
        log.exception("Ticket lobby: DB write failed", extra={"channel_id": target_id})
        await undo()
        raise LobbyError("save_failed") from None
    if failure is not None:
        await undo()
        raise failure

    # 5. 管理身分組的增減套用到既有的私人頻道
    failures: list[ApplyFailure] = []
    if old is not None:
        added = sorted(set(v.manager_role_ids) - set(old["manager_role_ids"]))
        removed = sorted(set(old["manager_role_ids"]) - set(v.manager_role_ids))
        if added or removed:
            tickets = _db(
                lambda: [
                    _Ticket(t.channel_id, t.closed_at, t.locked_overwrites_json)
                    for t in sqldb.list_lobby_ticket_channels(target_id)
                ]
            )
            failures, json_updates = await apply_manager_role_changes(guild, tickets, added, removed, v.reason)  # pyright: ignore[reportArgumentType]
            if json_updates:
                _db(lambda: sqldb.set_ticket_locked_overwrites(json_updates))
    return SaveResult(target_id, message.id, message.jump_url, failures)


async def remove_lobby(guild: discord.Guild, lobby_channel_id: int) -> bool:
    """移除大廳：拿掉大廳訊息的開單按鈕（訊息與頻道保留），標記已移除，底下的私人頻道改為未歸屬（同一個交易）。

    訊息或頻道已不存在視為已拿掉。呼叫端須先確認伺服器不是 unavailable，頻道不在快取才代表真的被刪。
    bot 對大廳頻道缺權限（Forbidden）時，仍然標示移除，讓大廳不再接受開單；按鈕沒拿掉，回傳 False 讓呼叫端說明。

    Returns:
        按鈕是否已拿掉（或訊息本來就不在）。

    Raises:
        LobbyError: discord_error（其他 Discord 錯誤，大廳沒有移除）、save_failed（資料庫寫入失敗）。
    """
    async with _locked(lobby_channel_id):
        # 訊息 ID 在鎖裡重讀：等鎖期間若有修改重發了大廳訊息，要拿掉的是新的那則
        snap = _db(lambda: sqldb.get_ticket_lobby_snapshot(lobby_channel_id))
        if snap is None or snap["removed_at"] is not None:
            return True
        button_removed = True
        channel = guild.get_channel(lobby_channel_id)
        if channel is not None:
            try:
                message = await channel.fetch_message(snap["message_id"])  # pyright: ignore[reportAttributeAccessIssue]
                await message.edit(view=None)
            except discord.NotFound:
                pass
            except discord.Forbidden:
                button_removed = False
            except discord.HTTPException as e:
                raise _http_error(e) from None
        try:
            _db(lambda: sqldb.remove_ticket_lobby(lobby_channel_id))
        except Exception:
            log.exception("Ticket lobby: DB write failed on remove", extra={"channel_id": lobby_channel_id})
            raise LobbyError("save_failed") from None
        return button_removed


# ====== 開單（P-03） ======
OpenRefusal = Literal["lobby_removed", "lobby_invalid", "already_open", "full", "discord_error", "save_failed"]


class TicketOpenError(Exception):
    """開單被拒或失敗。`existing_channel_id` 是 already_open 時使用者已有的頻道；`message` 是 Discord 回的說明（discord_error 時）。"""

    def __init__(self, code: OpenRefusal, *, existing_channel_id: int | None = None, message: str | None = None):
        super().__init__(code, existing_channel_id, message)
        self.code = code
        self.existing_channel_id = existing_channel_id
        self.message = message


@dataclass(frozen=True)
class _LobbySettings:
    channel_id: int
    message_id: int
    ticket_category_id: int | None
    manager_role_ids: list[int]


def ticket_channel_name(prefix: str, number: int) -> str:
    """私人頻道名稱「前綴-四位流水號」；超過 9999 照常往上加。"""
    return f"{prefix}-{number:04d}"


async def open_ticket(guild: discord.Guild, lobby_channel_id: int, creator: discord.Member) -> discord.TextChannel:
    """從大廳開一張私人頻道，持有該大廳的鎖，同時按下的人依序處理，不會超過限制。

    1. 大廳已移除（或不屬於這個伺服器）、失效（`lobby_invalid_reason`）時拒絕。
    2. 先清掉大廳底下 Discord 已不存在的私人頻道紀錄，再檢查每人一張與上限（未刪除的都算，含已鎖定）。
    3. 取流水號（不回收），在大廳設定的分類用 `build_ticket_overwrites` 建立頻道，送出並置頂操作訊息，寫入紀錄。
       頻道建立後送訊息或寫資料庫失敗時刪除頻道；置頂失敗只記 log。

    Raises:
        TicketOpenError: 見 `OpenRefusal`。
    """
    async with lobby_lock(lobby_channel_id):
        return await _open_ticket(guild, lobby_channel_id, creator)


async def _open_ticket(guild: discord.Guild, lobby_channel_id: int, creator: discord.Member) -> discord.TextChannel:
    snap = _db(lambda: sqldb.get_ticket_lobby_snapshot(lobby_channel_id))
    if snap is None or snap["removed_at"] is not None or snap["guild_id"] != guild.id:
        raise TicketOpenError("lobby_removed")
    lobby = _LobbySettings(snap["channel_id"], snap["message_id"], snap["ticket_category_id"], snap["manager_role_ids"])
    if await lobby_invalid_reason(guild, lobby) is not None:
        raise TicketOpenError("lobby_invalid")

    def check_limits() -> tuple[int | None, int]:
        gone = [t.channel_id for t in sqldb.list_lobby_ticket_channels(lobby_channel_id) if guild.get_channel(t.channel_id) is None]
        sqldb.delete_ticket_channels(gone)
        existing = sqldb.find_user_ticket(lobby_channel_id, creator.id) if snap["one_per_user"] else None
        return existing, sqldb.count_open_lobby_tickets(lobby_channel_id)

    existing, count = _db(check_limits)
    if existing is not None:
        raise TicketOpenError("already_open", existing_channel_id=existing)
    if snap["max_open"] is not None and count >= snap["max_open"]:
        raise TicketOpenError("full")

    number = _db(lambda: sqldb.take_ticket_number(lobby_channel_id))
    if number is None:
        raise TicketOpenError("lobby_removed")
    category = guild.get_channel(lobby.ticket_category_id)  # pyright: ignore[reportArgumentType]
    reason = audit_reason(creator, f"從大廳 {lobby_channel_id} 開立私人頻道", via_dashboard=False)
    try:
        channel = await category.create_text_channel(  # pyright: ignore[reportAttributeAccessIssue, reportOptionalMemberAccess]
            name=ticket_channel_name(snap["name_prefix"], number),
            topic=f"Ticket channel for {creator} ({creator.id})",
            overwrites=build_ticket_overwrites(category, lobby, creator, guild.me),  # pyright: ignore[reportArgumentType]
            reason=reason,
        )
    except discord.HTTPException as e:
        raise TicketOpenError("discord_error", message=e.text or str(e)) from None

    try:
        msg = await channel.send(
            f"{creator.mention}，你好！請在此頻道描述你的問題，我們會盡快協助你。", view=TicketChannelView(channel.id, locked=False)
        )
    except discord.HTTPException as e:
        await _delete_quietly(channel, "ticket channel", reason)
        raise TicketOpenError("discord_error", message=e.text or str(e)) from None

    try:
        _db(
            lambda: sqldb.merge(
                TicketChannel(
                    channel_id=channel.id,
                    guild_id=guild.id,
                    creator_id=creator.id,
                    created_at=nowtz(),
                    view_message_id=msg.id,
                    lobby_channel_id=lobby_channel_id,
                    number=number,
                )
            )
        )
    except Exception:
        log.exception("Ticket: DB write failed on open", extra={"lobby_channel_id": lobby_channel_id})
        await _delete_quietly(channel, "ticket channel", reason)
        raise TicketOpenError("save_failed") from None

    try:
        await msg.pin()
    except discord.HTTPException:
        log.warning("Ticket: failed to pin the control message", extra={"channel_id": channel.id})
    return channel
