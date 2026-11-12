"""私人頻道大廳的共用規則：大廳是否失效、bot 缺少的權限、前綴與預設內容、私人頻道的權限覆寫。

網頁後台與 bot 內部共用，兩邊的判斷才會一致。不依賴 view；需要建立大廳訊息的流程在 `starDiscord/ticket_lobby.py`。
讀寫 Discord 物件的函式必須在 bot 的事件迴圈上呼叫。
"""

import json
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

import discord

from starlib.message_content import EmbedAuthor, EmbedContent, MessageContent
from starlib.reaction_roles import PermissionIssue

log = logging.getLogger(__name__)

#: 大廳開單按鈕的預設文字
DEFAULT_BUTTON_LABEL = "建立私人頻道"
#: 私人頻道名稱前綴（正規化後）的最大長度
MAX_PREFIX_LENGTH = 20
#: 同時開啟上限的範圍上限（下限 1，不限制存 null）
MAX_OPEN_LIMIT = 10000
#: 開單按鈕文字的上限（Discord 按鈕 label）
MAX_BUTTON_LABEL = 80
#: 開單按鈕 emoji 的上限（欄位長度）
MAX_BUTTON_EMOJI = 100

#: 大廳失效的原因：大廳頻道被刪、私人頻道所在的分類被刪（或從未設定）、大廳訊息被刪
LobbyInvalidReason = Literal["channel_deleted", "category_deleted", "message_deleted"]


class LobbyRef(Protocol):
    """檢查大廳需要的欄位；`TicketChannelLobby` 與後台不綁 session 的快照都符合。"""

    @property
    def channel_id(self) -> int: ...

    @property
    def message_id(self) -> int: ...

    @property
    def ticket_category_id(self) -> int | None: ...


@dataclass(frozen=True)
class TicketPermissionIssue(PermissionIssue):
    #: 檢查的位置：私人頻道所在的分類，或大廳頻道
    target: Literal["category", "lobby_channel"]


async def lobby_invalid_reason(guild: discord.Guild, lobby: LobbyRef) -> LobbyInvalidReason | None:
    """大廳失效的原因，沒有失效回 None；同時有多項只回第一個（頻道、分類、訊息的順序）。

    大廳訊息只有確定 NotFound 才算失效；缺權限或暫時性錯誤讀不到時不能判斷為失效。
    """
    channel = guild.get_channel(lobby.channel_id)
    if channel is None:
        return "channel_deleted"
    category = guild.get_channel(lobby.ticket_category_id) if lobby.ticket_category_id is not None else None
    if category is None or category.type != discord.ChannelType.category:
        return "category_deleted"
    fetch_message = getattr(channel, "fetch_message", None)
    if fetch_message is not None:
        try:
            await fetch_message(lobby.message_id)
        except discord.NotFound:
            return "message_deleted"
        except discord.Forbidden, discord.HTTPException:
            pass
    return None


#: bot 需要的權限，順序固定：(位置, Permissions 屬性, 顯示名稱, 缺少時的後果)
_REQUIRED_PERMISSIONS: list[tuple[Literal["category", "lobby_channel"], str, str, str]] = [
    ("category", "manage_channels", "Manage Channels", "無法建立或刪除私人頻道"),
    ("category", "manage_roles", "Manage Roles", "無法設定私人頻道的可見範圍，也無法鎖定、重開"),
    ("lobby_channel", "view_channel", "View Channel", "無法發送或更新大廳訊息"),
    ("lobby_channel", "read_message_history", "Read Message History", "無法更新或移除大廳訊息"),
    ("lobby_channel", "send_messages", "Send Messages", "無法發送大廳訊息"),
    ("lobby_channel", "embed_links", "Embed Links", "大廳訊息的 embed 無法顯示"),
    ("category", "manage_messages", "Manage Messages", "無法置頂私人頻道的操作訊息"),
]


def _missing(
    where: Literal["category", "lobby_channel"], channel: discord.abc.GuildChannel | None, me: discord.Member
) -> dict[str, TicketPermissionIssue]:
    """某個位置缺少的權限（屬性名稱 → 說明）；位置不存在回空 dict。"""
    if channel is None:
        return {}
    perms = channel.permissions_for(me)
    return {
        attr: TicketPermissionIssue(name, "channel", consequence, target)
        for target, attr, name, consequence in _REQUIRED_PERMISSIONS
        if target == where and not getattr(perms, attr)
    }


def category_permission_issues(
    guild: discord.Guild, category: discord.abc.GuildChannel | None
) -> list[TicketPermissionIssue]:
    """bot 在「私人頻道所在分類」缺少的權限；分類不存在回空 list。"""
    return list(_missing("category", category, guild.me).values())


def lobby_channel_permission_issues(
    guild: discord.Guild, channel: discord.abc.GuildChannel | None
) -> list[TicketPermissionIssue]:
    """bot 在「大廳頻道」缺少的權限；頻道不存在回空 list。"""
    return list(_missing("lobby_channel", channel, guild.me).values())


def bot_permission_issues(guild: discord.Guild, lobby: LobbyRef) -> list[TicketPermissionIssue]:
    """bot 缺少的權限，全部具備回空 list；順序固定（分類的 Manage Channels、Manage Roles，大廳頻道的 View、Read Message History、Send、Embed，分類的 Manage Messages）。

    分類或大廳頻道已不存在時略過該位置，由 `lobby_invalid_reason` 說明。
    """
    category = guild.get_channel(lobby.ticket_category_id) if lobby.ticket_category_id is not None else None
    missing = {
        "category": _missing("category", category, guild.me),
        "lobby_channel": _missing("lobby_channel", guild.get_channel(lobby.channel_id), guild.me),
    }
    return [missing[where][attr] for where, attr, *_ in _REQUIRED_PERMISSIONS if attr in missing[where]]


def normalize_prefix(raw: str) -> str:
    """私人頻道名稱前綴照 Discord 頻道名稱的規則處理：轉小寫、空白換成 `-`、只留字母數字（含 Unicode）、`-`、`_`，連續的 `-` 合併、去掉頭尾的 `-`。"""
    text = re.sub(r"\s+", "-", raw.strip().lower())
    text = "".join(ch for ch in text if ch.isalnum() or ch in "-_")
    return re.sub(r"-{2,}", "-", text).strip("-")


def prefix_error(raw: str) -> str | None:
    """前綴正規化後不是 1 到 20 個字元時的說明，合格回 None。"""
    length = len(normalize_prefix(raw))
    if not 1 <= length <= MAX_PREFIX_LENGTH:
        return f"處理後必須是 1 到 {MAX_PREFIX_LENGTH} 個字元（目前 {length} 個）"
    return None


def default_lobby_content(avatar_url: str | None) -> MessageContent:
    """大廳沒有存下內容時沿用的預設訊息（與測試版 `/ticket setup` 相同）。"""
    return MessageContent(
        embed=EmbedContent(
            color=0xC4E9FF,
            author=EmbedAuthor(name="私人頻道系統", icon_url=avatar_url),
            description="點擊下方按鈕以建立私人頻道",
        )
    )


def overwrite_key(kind: Literal["role", "member"], target_id: int) -> str:
    """`locked_overwrites_json` 的鍵：`role:<id>` 或 `member:<id>`。"""
    return f"{kind}:{target_id}"


def open_overwrite() -> discord.PermissionOverwrite:
    """開啟中的私人頻道，建立者、管理身分組與 bot 的覆寫。"""
    return discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)


def locked_overwrite() -> discord.PermissionOverwrite:
    """已鎖定的私人頻道，管理身分組看得到但不能發言。"""
    return discord.PermissionOverwrite(view_channel=True, send_messages=False, read_message_history=True)


class ManagerLobbyRef(Protocol):
    @property
    def manager_role_ids(self) -> list[int]: ...


def build_ticket_overwrites(
    category: discord.CategoryChannel,
    lobby: ManagerLobbyRef,
    creator: discord.Member | discord.User,
    me: discord.Member,
) -> dict[discord.Role | discord.Member | discord.User, discord.PermissionOverwrite]:
    """新私人頻道的權限覆寫：複製分類的覆寫，@everyone 看不到；建立者、管理身分組與 bot 能查看、發言、讀紀錄。

    已不存在的管理身分組略過。沒設管理身分組時，只有分類覆寫原本看得到的身分組、建立者與 bot 看得到。
    """
    guild = category.guild
    overwrites: dict = dict(category.overwrites)
    overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=False)
    for role_id in lobby.manager_role_ids:
        role = guild.get_role(role_id)
        if role is not None:
            overwrites[role] = open_overwrite()
    overwrites[creator] = open_overwrite()
    overwrites[me] = open_overwrite()
    return overwrites


class TicketRef(Protocol):
    @property
    def channel_id(self) -> int: ...

    @property
    def closed_at(self) -> datetime | None: ...

    @property
    def locked_overwrites_json(self) -> str | None: ...


@dataclass(frozen=True)
class ApplyFailure:
    channel_id: int
    reason: str


async def apply_manager_role_changes(
    guild: discord.Guild, tickets: Iterable[TicketRef], added: Iterable[int], removed: Iterable[int], reason: str
) -> tuple[list[ApplyFailure], dict[int, str]]:
    """把管理身分組的增減套用到大廳底下的私人頻道。

    - 新增：開啟中的頻道給查看、發言、讀紀錄；已鎖定的只給查看與讀紀錄，`locked_overwrites_json` 不為 None 時另記 `role:<id>: true`，重開後才能發言。
    - 移除：刪掉覆寫；已鎖定的頻道一併刪掉 `locked_overwrites_json` 裡該身分組的鍵，重開時才不會復活。
    - 頻道或身分組不在 guild 快取：略過（身分組被刪時 Discord 已清掉覆寫）。呼叫端須先確認伺服器不是 unavailable。
    - 單一頻道失敗不中斷，記在回傳的失敗清單；該頻道已成功的部分仍會反映在回傳的 JSON。

    Returns:
        (失敗清單, 需要寫回資料庫的 `locked_overwrites_json`：頻道 ID → 新 JSON)
    """
    added_roles = [r for r in (guild.get_role(rid) for rid in added) if r is not None]
    removed_roles = [r for r in (guild.get_role(rid) for rid in removed) if r is not None]
    failures: list[ApplyFailure] = []
    json_updates: dict[int, str] = {}
    for ticket in tickets:
        channel = guild.get_channel(ticket.channel_id)
        if channel is None:
            continue
        locked = ticket.closed_at is not None
        # 已經成功的部分要記下來：同一個頻道中途失敗時，成功的那些覆寫仍要反映在 locked_overwrites_json
        done_added: list[discord.Role] = []
        done_removed: list[discord.Role] = []
        try:
            for role in added_roles:
                await channel.set_permissions(
                    role, overwrite=locked_overwrite() if locked else open_overwrite(), reason=reason
                )
                done_added.append(role)
            for role in removed_roles:
                await channel.set_permissions(role, overwrite=None, reason=reason)
                done_removed.append(role)
        except discord.Forbidden:
            failures.append(ApplyFailure(ticket.channel_id, "我缺少這個頻道的 Manage Roles 或 Manage Channels 權限"))
        except discord.HTTPException as e:
            failures.append(ApplyFailure(ticket.channel_id, e.text or str(e)))
        if locked and ticket.locked_overwrites_json is not None and (done_added or done_removed):
            try:
                saved = json.loads(ticket.locked_overwrites_json)
            except ValueError:
                log.warning("Invalid locked_overwrites_json", extra={"channel_id": ticket.channel_id})
                continue
            for role in done_added:
                saved[overwrite_key("role", role.id)] = True
            for role in done_removed:
                saved.pop(overwrite_key("role", role.id), None)
            json_updates[ticket.channel_id] = json.dumps(saved, ensure_ascii=False)
    return failures, json_updates


# ====== 鎖定、重開與刪除（P-04） ======
TicketAction = Literal["lock", "reopen", "delete"]


def allowed_ticket_actions(*, is_creator: bool, is_manager: bool, manage_channels: bool) -> set[TicketAction]:
    """Discord 內按鈕的權限（規格〈鎖定、重開與刪除〉的對照表）。

    `is_creator`、`is_manager` 只在私人頻道屬於還在使用的大廳時才傳 True：未歸屬或大廳已移除的頻道只剩伺服器層級
    Manage Channels 的人能操作。後台的權限另由區塊權限（Manage Channels）判斷，不經這裡。
    """
    if manage_channels or is_manager:
        return {"lock", "reopen", "delete"}
    if is_creator:
        return {"lock"}
    return set()


def raw_overwrites(channel: discord.abc.GuildChannel) -> list[tuple[str, discord.abc.Snowflake, discord.PermissionOverwrite]]:
    """頻道的全部覆寫：(鍵, 套用時的對象, 覆寫)。鍵見 `overwrite_key`。

    讀 Discord 原始的覆寫清單，不用 `channel.overwrites`：後者會略過不在成員快取的成員，整批 `edit` 時那些覆寫會被刪掉。
    不在快取的成員用 `discord.Object`（py-cord 會當成成員覆寫送出）；已刪除的身分組略過（Discord 已清掉覆寫）。
    """
    guild = channel.guild
    result: list[tuple[str, discord.abc.Snowflake, discord.PermissionOverwrite]] = []
    for ow in channel._overwrites:  # noqa: SLF001 見 docstring
        overwrite = discord.PermissionOverwrite.from_pair(discord.Permissions(ow.allow), discord.Permissions(ow.deny))
        if ow.is_role():
            role = guild.get_role(ow.id)
            if role is not None:
                result.append((overwrite_key("role", ow.id), role, overwrite))
        else:
            target = guild.get_member(ow.id) or discord.Object(ow.id)
            result.append((overwrite_key("member", ow.id), target, overwrite))
    return result


def _with_send(overwrite: discord.PermissionOverwrite, value: bool | None) -> discord.PermissionOverwrite:
    allow, deny = overwrite.pair()
    copied = discord.PermissionOverwrite.from_pair(allow, deny)
    copied.send_messages = value
    return copied


def locked_overwrites(channel: discord.abc.GuildChannel, me: discord.abc.Snowflake) -> tuple[dict, dict[str, bool | None]]:
    """鎖定後的覆寫：bot 以外所有覆寫對象都不能發言，其他權限不變；bot 的成員覆寫確保能發言（沒有就加上）。

    Returns:
        (要整批套用的覆寫, 要存進 `locked_overwrites_json` 的鎖定前 `send_messages`；bot 不記)
    """
    me_key = overwrite_key("member", me.id)
    overwrites: dict = {}
    saved: dict[str, bool | None] = {}
    bot_overwrite = discord.PermissionOverwrite()
    for key, target, overwrite in raw_overwrites(channel):
        if key == me_key:
            bot_overwrite = overwrite
            continue
        saved[key] = overwrite.send_messages
        overwrites[target] = _with_send(overwrite, False)
    overwrites[me] = _with_send(bot_overwrite, True)
    return overwrites, saved


def reopened_overwrites(
    channel: discord.abc.GuildChannel,
    me: discord.abc.Snowflake,
    saved: dict[str, bool | None] | None,
    *,
    creator_id: int,
    manager_role_ids: Iterable[int],
) -> dict:
    """重開後的覆寫：只改 `send_messages`，其他權限不變；bot 的覆寫不動。

    - 有保存值（`saved` 不為 None）：恢復成鎖定前的值；鎖定後才加上的對象（沒有保存值）維持現狀。
    - 沒有保存值（測試版鎖定的頻道）：建立者、管理身分組與 bot 恢復發言（測試版鎖定時連 bot 也鎖），
      其餘回到所在分類對該對象的 `send_messages`（分類沒有覆寫該對象時為未設定）。

    Args:
        manager_role_ids: 所屬大廳現行的管理身分組；未歸屬或大廳已移除時傳空的。
    """
    me_key = overwrite_key("member", me.id)
    managers = {overwrite_key("role", rid) for rid in manager_role_ids}
    creator = overwrite_key("member", creator_id)
    category_send: dict[str, bool | None] = {}
    category = getattr(channel, "category", None)
    if saved is None and category is not None:
        category_send = {key: o.send_messages for key, _, o in raw_overwrites(category)}
    overwrites: dict = {}
    for key, target, overwrite in raw_overwrites(channel):
        if key == me_key:
            overwrites[target] = overwrite if saved is not None else _with_send(overwrite, True)
        elif saved is not None:
            overwrites[target] = _with_send(overwrite, saved[key]) if key in saved else overwrite
        elif key == creator or key in managers:
            overwrites[target] = _with_send(overwrite, True)
        else:
            overwrites[target] = _with_send(overwrite, category_send.get(key))
    return overwrites


def parse_locked_overwrites(raw: str | None) -> dict[str, bool | None] | None:
    """讀 `locked_overwrites_json`；null 或格式錯誤回 None（照預設規則重開）。"""
    if raw is None:
        return None
    try:
        value = json.loads(raw)
    except ValueError:
        log.warning("Invalid locked_overwrites_json")
        return None
    return value if isinstance(value, dict) else None
