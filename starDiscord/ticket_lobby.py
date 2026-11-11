"""私人頻道大廳的建立、更新與移除：網頁後台與 `/ticket setup`（P-05）共用。

依賴 `TicketLobbyView`，所以放在 starDiscord；不依賴 view 的規則在 `starlib/tickets.py`。
全部讀寫 Discord 物件，必須在 bot 的事件迴圈上呼叫。錯誤一律丟 `LobbyError`，由呼叫端轉成自己的回應。
"""

import logging
from dataclasses import dataclass, field
from typing import Literal

import discord

from starlib import sclient, sqldb
from starlib.message_content import MessageContent, from_json, to_json, to_send_kwargs
from starlib.tickets import ApplyFailure, apply_manager_role_changes, default_lobby_content

from .uiElement.view import TicketLobbyView

log = logging.getLogger(__name__)

LobbyErrorCode = Literal[
    "channel_not_found",
    "category_not_found",
    "channel_in_use",
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


async def _delete_quietly(target: discord.Message | discord.abc.GuildChannel, what: str) -> None:
    try:
        await target.delete()
    except discord.HTTPException:
        log.exception("Ticket lobby: failed to delete %s", what)


def _bot_avatar(guild: discord.Guild) -> str | None:
    avatar = getattr(guild.me, "display_avatar", None)
    return avatar.url if avatar is not None else None


async def save_lobby(guild: discord.Guild, v: LobbyValues) -> SaveResult:
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
            await _delete_quietly(created, "created channel")
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
            await _delete_quietly(created, "created channel")

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


async def remove_lobby(guild: discord.Guild, lobby_channel_id: int, message_id: int) -> None:
    """移除大廳：拿掉大廳訊息的開單按鈕（訊息與頻道保留），標記已移除，底下的私人頻道改為未歸屬。

    訊息或頻道已不存在視為已拿掉。呼叫端須先確認伺服器不是 unavailable，頻道不在快取才代表真的被刪。

    Raises:
        LobbyError: discord_error（拿不掉按鈕）、save_failed（資料庫寫入失敗）。
    """
    channel = guild.get_channel(lobby_channel_id)
    if channel is not None:
        try:
            message = await channel.fetch_message(message_id)  # pyright: ignore[reportAttributeAccessIssue]
            await message.edit(view=None)
        except discord.NotFound:
            pass
        except discord.HTTPException as e:
            raise _http_error(e) from None
    try:
        _db(lambda: sqldb.mark_lobby_removed(lobby_channel_id))
        _db(lambda: sqldb.unassign_lobby_tickets(lobby_channel_id))
    except Exception:
        log.exception("Ticket lobby: DB write failed on remove", extra={"channel_id": lobby_channel_id})
        raise LobbyError("save_failed") from None
