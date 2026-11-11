"""私人頻道大廳的共用規則：大廳是否失效、bot 缺少的權限。

網頁後台與 bot 內部共用，兩邊的判斷才會一致。全部讀 Discord 物件，必須在 bot 的事件迴圈上呼叫。
"""

from dataclasses import dataclass
from typing import Literal, Protocol

import discord

from starlib.reaction_roles import PermissionIssue

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


def bot_permission_issues(guild: discord.Guild, lobby: LobbyRef) -> list[TicketPermissionIssue]:
    """bot 缺少的權限，全部具備回空 list；順序固定（分類的 Manage Channels、Manage Roles，大廳頻道的 View、Send、Embed，分類的 Manage Messages）。

    分類或大廳頻道已不存在時略過該位置，由 `lobby_invalid_reason` 說明。
    """
    me = guild.me
    category = guild.get_channel(lobby.ticket_category_id) if lobby.ticket_category_id is not None else None
    channel = guild.get_channel(lobby.channel_id)
    category_perms = category.permissions_for(me) if category is not None else None
    channel_perms = channel.permissions_for(me) if channel is not None else None

    checks: list[tuple[discord.Permissions | None, str, str, str, Literal["category", "lobby_channel"]]] = [
        (category_perms, "manage_channels", "Manage Channels", "無法建立或刪除私人頻道", "category"),
        (category_perms, "manage_roles", "Manage Roles", "無法設定私人頻道的可見範圍，也無法鎖定、重開", "category"),
        (channel_perms, "view_channel", "View Channel", "無法發送或更新大廳訊息", "lobby_channel"),
        (channel_perms, "send_messages", "Send Messages", "無法發送大廳訊息", "lobby_channel"),
        (channel_perms, "embed_links", "Embed Links", "大廳訊息的 embed 無法顯示", "lobby_channel"),
        (category_perms, "manage_messages", "Manage Messages", "無法置頂私人頻道的操作訊息", "category"),
    ]
    return [
        TicketPermissionIssue(name, "channel", consequence, target)
        for perms, attr, name, consequence, target in checks
        if perms is not None and not getattr(perms, attr)
    ]
