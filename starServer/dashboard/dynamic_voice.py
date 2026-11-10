"""動態語音大廳：
GET    /dashboard/guilds/{id}/dynamic-voice          大廳一覽
GET    /dashboard/guilds/{id}/dynamic-voice/options  表單的頻道選項與登入者的 username
PUT    /dashboard/guilds/{id}/dynamic-voice          body `{values, original}`，original 為 null 是新增
DELETE /dashboard/guilds/{id}/dynamic-voice          body `{original}`

大廳與模板的欄位名稱統一為 `channel_id`、`template`，對應資料表的 `channel_id`、`default_room_name`。
修改與刪除用條件式寫入（WHERE 帶原始值），後到的一定被擋下並回 409 conflict；新增遇到已存在回 409 already_exists。
大廳 cache 由 repository 方法同步，這裡不碰。
"""

import discord
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from starlib import sqldb
from starlib.dynamic_voice import lobby_permission_issues, normalize_room_template, room_template_too_long
from starlib.exceptions import DataExistError

from .access import on_guild, require_guild_access
from .conflict import Conflict
from .db import run_db
from .errors import DashboardError
from .session import SessionInfo, require_session

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


class LobbyValues(BaseModel):
    #: Discord ID 用字串
    channel_id: str
    template: str | None = None


class PutBody(BaseModel):
    values: LobbyValues
    #: 打開表單時看到的值；null 表示新增
    original: LobbyValues | None = None


class DeleteBody(BaseModel):
    original: LobbyValues


def _channel_id(raw: str) -> int:
    try:
        return int(raw)
    except ValueError:
        raise DashboardError(400, "invalid_request") from None


def _db_values(values: LobbyValues) -> dict[str, int | str | None]:
    """對外欄位轉成資料表欄位；template 保持原樣（original 要和資料庫的原始值比對，不能正規化）。"""
    return {"channel_id": _channel_id(values.channel_id), "default_room_name": values.template}


def _check_lobby_choice(guild: discord.Guild, channel_id: int) -> None:
    """在 bot 的事件迴圈上呼叫：必須是該伺服器的語音頻道，而且不是目前存在的動態房間。"""
    channel = guild.get_channel(channel_id)
    if channel is None or channel.type != discord.ChannelType.voice or channel_id in sqldb.cache.dynamic_voice_room:
        raise DashboardError(400, "invalid_request", field="channel_id")


def _options(guild: discord.Guild, user_id: int) -> dict:
    """在 bot 的事件迴圈上呼叫。username 與 bot 開房時代入 `{member}` 的值同一個來源（member.name）。"""
    member = guild.get_member(user_id)
    return {
        "channels": [
            {
                "id": str(c.id),
                "name": c.name,
                "category": c.category.name if c.category is not None else None,
                "permission_issues": [{"permission": i.permission, "scope": i.scope, "consequence": i.consequence} for i in lobby_permission_issues(c)],
            }
            for c in guild.voice_channels
            if c.id not in sqldb.cache.dynamic_voice_room
        ],
        "username": member.name if member is not None else None,
    }


@router.get("/guilds/{guild_id}/dynamic-voice/options")
async def get_dynamic_voice_options(guild_id: int = Depends(require_guild_access), info: SessionInfo = Depends(require_session)):
    return await on_guild(guild_id, lambda guild: _options(guild, int(info.discord_user_id)))


def _conflict(guild_id: int) -> DashboardError:
    return Conflict(current_values(guild_id)).to_error()


@router.put("/guilds/{guild_id}/dynamic-voice")
async def put_dynamic_voice(body: PutBody, guild_id: int = Depends(require_guild_access)):
    channel_id = _channel_id(body.values.channel_id)
    template = normalize_room_template(body.values.template)
    if room_template_too_long(template):
        raise DashboardError(400, "invalid_request", field="template")
    await on_guild(guild_id, lambda guild: _check_lobby_choice(guild, channel_id))

    values = {"channel_id": channel_id, "default_room_name": template}
    original = None if body.original is None else _db_values(body.original)

    def _write() -> None:
        if original is None:
            try:
                sqldb.insert_dynamic_voice_lobby(guild_id, channel_id, template)
            except DataExistError:
                raise DashboardError(409, "already_exists", current=current_values(guild_id)) from None
        elif sqldb.update_dynamic_voice_lobby_if(guild_id, original, values) == 0:
            raise _conflict(guild_id)

    await run_db(_write)
    return await lobby_response(guild_id, {"channel_id": str(channel_id), "template": template})


@router.delete("/guilds/{guild_id}/dynamic-voice")
async def delete_dynamic_voice(body: DeleteBody, guild_id: int = Depends(require_guild_access)):
    original = _db_values(body.original)

    def _delete() -> None:
        if sqldb.delete_dynamic_voice_lobby_if(guild_id, original) == 0:
            raise _conflict(guild_id)

    await run_db(_delete)
    return {"ok": True}
