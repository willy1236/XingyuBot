"""頻道與身分組的有效性判斷：bot 能不能對它發訊息、tag 它。

這兩個函式讀 Discord 物件，必須在 bot 的事件迴圈上呼叫（經 access.on_guild）。
有效回 None，失效回原因。
"""

import discord


def channel_invalid_reason(guild: discord.Guild, channel_id: int, scheduled: bool) -> str | None:
    channel = guild.get_channel(channel_id)
    if channel is None:
        return "頻道不存在"
    if channel.type not in (discord.ChannelType.text, discord.ChannelType.news):
        return "不支援的頻道類型"
    me = guild.me
    if me is None:
        return "無法確認 bot 的權限"
    perms = channel.permissions_for(me)
    required = [
        ("View Channel", perms.view_channel),
        ("Send Messages", perms.send_messages),
        ("Embed Links", perms.embed_links),
    ]
    if scheduled:
        required.append(("Read Message History", perms.read_message_history))
    missing = [name for name, ok in required if not ok]
    if missing:
        return "bot 缺少 " + "、".join(missing)
    return None


def role_invalid_reason(guild: discord.Guild, role_id: int) -> str | None:
    role = guild.get_role(role_id)
    if role is None:
        return "身分組不存在"
    if role.is_default():
        return "@everyone 不能使用"
    # bot 自己的身分組一定是 managed
    if role.managed:
        return "由 bot 或整合服務管理，無法使用"
    me = guild.me
    if not role.mentionable and not (me is not None and me.guild_permissions.mention_everyone):
        return "bot 無法 tag（未開啟「允許任何人提及」）"
    return None
