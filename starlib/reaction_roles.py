"""反應身分組的共用規則：身分組可否發放、按鈕 emoji 是否有效、bot 權限檢查。

網頁後台與 `/reactrole` 指令共用，兩邊的判斷才會一致。
全部讀 Discord 物件，必須在 bot 的事件迴圈上呼叫。
"""

from dataclasses import dataclass
from typing import Literal

import discord


@dataclass(frozen=True)
class PermissionIssue:
    #: 缺少的權限名稱，例如 "Manage Roles"
    permission: str
    #: 檢查的位置：伺服器層級，或訊息所在頻道
    scope: Literal["guild", "channel"]
    #: 缺少時的後果（中文）
    consequence: str


def role_issue(guild: discord.Guild, role: discord.Role | None) -> str | None:
    """身分組不能由 bot 發放的原因（中文），可以發放回 None。

    身分組不存在、@everyone 或由整合服務管理、位階不低於 bot 最高身分組。
    """
    if role is None:
        return "身分組不存在"
    if role.is_default() or role.managed:
        return "無法設定 @everyone 或由整合服務管理的身分組"
    if role >= guild.me.top_role:
        return "此身分組不低於我的最高身分組，我無法發放"
    return None


#: 身分組帶有這些權限時，任何人按下按鈕都會取得；只警告不擋，與 `/reactrole add` 一致
DANGEROUS_PERMISSIONS = (
    "administrator",
    "manage_guild",
    "manage_roles",
    "manage_channels",
    "manage_webhooks",
    "manage_messages",
    "manage_nicknames",
    "kick_members",
    "ban_members",
    "moderate_members",
    "mention_everyone",
    "view_audit_log",
)


def dangerous_permissions(role: discord.Role) -> list[str]:
    """身分組帶有的危險權限（discord.Permissions 的屬性名稱），沒有回空 list。"""
    return [name for name in DANGEROUS_PERMISSIONS if getattr(role.permissions, name, False)]


def operator_rank_issue(guild: discord.Guild, actor: discord.Member, role: discord.Role) -> str | None:
    """操作者不能設定這個身分組的原因（中文），可以回 None。伺服器擁有者不受位階限制。"""
    if actor.id != guild.owner_id and role >= actor.top_role:
        return "只能設定低於你最高身分組的身分組"
    return None


def emoji_valid(guild: discord.Guild, emoji: str | None) -> bool:
    """按鈕的 emoji 是否可用。沒設定與 Unicode emoji 一律有效；自訂 emoji 必須還在這個伺服器。"""
    if not emoji:
        return True
    parsed = discord.PartialEmoji.from_str(emoji)
    if parsed.id is None:
        return True
    return guild.get_emoji(parsed.id) is not None


def bot_permission_issues(guild: discord.Guild, channel: discord.abc.GuildChannel | None) -> list[PermissionIssue]:
    """bot 缺少的權限，全部具備回空 list；順序固定。channel 為 None（頻道已不存在）時只檢查伺服器層級。"""
    me = guild.me
    issues: list[PermissionIssue] = []
    if not me.guild_permissions.manage_roles:
        issues.append(PermissionIssue("Manage Roles", "guild", "按下按鈕無法給予或移除身分組"))
    if channel is None:
        return issues
    perms = channel.permissions_for(me)
    if not perms.view_channel:
        issues.append(PermissionIssue("View Channel", "channel", "無法發送或更新訊息"))
    if not perms.send_messages:
        issues.append(PermissionIssue("Send Messages", "channel", "無法發送新訊息或重新發送"))
    if not perms.embed_links:
        issues.append(PermissionIssue("Embed Links", "channel", "embed 無法顯示"))
    if not perms.read_message_history:
        issues.append(PermissionIssue("Read Message History", "channel", "無法讀取既有訊息"))
    return issues
