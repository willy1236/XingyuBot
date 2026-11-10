"""動態語音大廳：
GET /dashboard/guilds/{id}/dynamic-voice  大廳一覽（唯讀）

大廳與模板的欄位名稱統一為 `channel_id`、`template`，對應資料表的 `channel_id`、`default_room_name`。
"""

import discord
from fastapi import APIRouter, Depends

from starlib import sqldb
from starlib.dynamic_voice import lobby_permission_issues, room_template_too_long

from .access import on_guild, require_guild_access
from .db import run_db

router = APIRouter(prefix="/dashboard")


def lobby_view(guild: discord.Guild, channel_id: int, template: str | None) -> dict:
    """一覽用的大廳資料；在 bot 的事件迴圈上呼叫。

    `template` 是資料庫的原始值，不正規化：前端拿它當衝突比對的 original。
    """
    channel = guild.get_channel(channel_id)
    invalid: str | None = None
    if channel is None:
        invalid = "頻道不存在"
    elif channel.type != discord.ChannelType.voice:
        invalid = "不支援的頻道類型"

    category = getattr(channel, "category", None)
    return {
        "channel": {
            "id": str(channel_id),
            "name": channel.name if channel is not None else None,
            "category": category.name if category is not None else None,
            "invalid": invalid,
        },
        "template": template,
        "template_invalid": "超過 100 個字元的上限" if room_template_too_long(template) else None,
        "permission_issues": []
        if invalid
        else [{"permission": i.permission, "scope": i.scope, "consequence": i.consequence} for i in lobby_permission_issues(channel)],  # pyright: ignore[reportArgumentType]
    }


def current_values(guild_id: int) -> dict[str, str | None] | None:
    """資料庫目前的大廳（欄位同 original，Discord ID 轉字串）；沒有設定回 None。同步 DB，要經 run_db。"""
    row = sqldb.get_dynamic_voice_lobby_fresh(guild_id)
    if row is None:
        return None
    return {"channel_id": str(row.channel_id), "template": row.default_room_name}


async def lobby_response(guild_id: int, values: dict[str, str | None] | None) -> dict:
    """`{ lobby }`：values 為 None 時 lobby 是 null。"""
    if values is None:
        return {"lobby": None}
    channel_id, template = int(values["channel_id"]), values["template"]  # pyright: ignore[reportArgumentType]
    return {"lobby": await on_guild(guild_id, lambda guild: lobby_view(guild, channel_id, template))}


@router.get("/guilds/{guild_id}/dynamic-voice")
async def get_dynamic_voice(guild_id: int = Depends(require_guild_access)):
    return await lobby_response(guild_id, await run_db(lambda: current_values(guild_id)))
