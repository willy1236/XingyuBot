"""GET /dashboard/guilds/{id}/options：通知編輯表單的頻道與身分組選項。"""

import discord
from fastapi import APIRouter, Depends, Query

from .access import on_guild, require_guild_access
from .errors import DashboardError
from .notify_fields import parse_key
from .validity import channel_invalid_reason, role_invalid_reason

router = APIRouter(prefix="/dashboard")


def _options(guild: discord.Guild, scheduled: bool) -> dict:
    """在 bot 的事件迴圈上呼叫。只列出有效性判斷認為有效的頻道與身分組。"""
    channels = [
        {"id": str(c.id), "name": c.name, "type": c.type.name}
        for c in sorted(guild.channels, key=lambda c: (c.position, c.id))
        if channel_invalid_reason(guild, c.id, scheduled) is None
    ]
    # guild.roles 由低到高，選單把高位的放前面
    roles = [
        {"id": str(r.id), "name": r.name, "color": f"#{r.color.value:06x}" if r.color.value else None}
        for r in reversed(guild.roles)
        if role_invalid_reason(guild, r.id) is None
    ]
    return {"channels": channels, "roles": roles}


@router.get("/guilds/{guild_id}/options")
async def get_options(notify_type: str = Query(), guild_id: int = Depends(require_guild_access)):
    try:
        spec = parse_key(notify_type)
    except KeyError:
        raise DashboardError(400, "invalid_request") from None
    return await on_guild(guild_id, lambda guild: _options(guild, spec.scheduled))
