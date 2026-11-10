"""動態語音大廳的共用規則：bot 權限檢查與房間名稱模板。

網頁後台與 `/channel voice` 指令共用，兩邊的判斷才會一致。
權限檢查讀 Discord 物件，必須在 bot 的事件迴圈上呼叫。
"""

from dataclasses import dataclass
from typing import Literal

import discord

#: Discord 頻道名稱的長度上限
MAX_ROOM_NAME = 100
#: Discord username 的長度上限，估算模板長度時代入 `{member}` 的字數
MAX_USERNAME = 32


@dataclass(frozen=True)
class LobbyPermIssue:
    #: 缺少的權限名稱，例如 "Manage Channels"
    permission: str
    #: 檢查的位置：大廳所在分類、伺服器層級，或大廳頻道本身
    scope: Literal["category", "guild", "channel"]
    #: 缺少時的後果（中文）
    consequence: str


def lobby_permission_issues(channel: discord.VoiceChannel) -> list[LobbyPermIssue]:
    """bot 在這個大廳缺少的權限，全部具備回空 list；順序固定。

    Manage Channels 有分類時看分類，沒有分類時看伺服器層級（房間會建立在最上層）。
    """
    me = channel.guild.me
    issues: list[LobbyPermIssue] = []

    if channel.category is not None:
        if not channel.category.permissions_for(me).manage_channels:
            issues.append(LobbyPermIssue("Manage Channels", "category", "無法建立房間"))
    elif not me.guild_permissions.manage_channels:
        issues.append(LobbyPermIssue("Manage Channels", "guild", "無法建立房間"))

    perms = channel.permissions_for(me)
    # 管理身分組權限需要經過額外的 OAuth 驗證
    if not perms.manage_roles:
        issues.append(LobbyPermIssue("Manage Roles", "channel", "房間建立者拿不到房間的管理權限"))
    if not perms.move_members:
        issues.append(LobbyPermIssue("Move Members", "channel", "無法把進入大廳的人移進房間"))
    if not perms.send_messages:
        issues.append(LobbyPermIssue("Send Messages", "channel", "出錯時無法在大廳提示使用者"))
    if not perms.view_channel:
        issues.append(LobbyPermIssue("View Channel", "channel", "偵測不到有人進入大廳"))
    return issues


def normalize_room_template(raw: str | None) -> str | None:
    """去頭尾空白，空字串視為未設定。"""
    if raw is None:
        return None
    stripped = raw.strip()
    return stripped or None


def room_template_too_long(template: str | None) -> bool:
    """把 `{member}` 當成最長的 username 估算，房名是否超過 Discord 的上限。"""
    if template is None:
        return False
    return len(template.replace("{member}", "x" * MAX_USERNAME)) > MAX_ROOM_NAME
