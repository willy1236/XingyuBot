"""動態房間：
GET  /dashboard/guilds/{id}/dynamic-voice/rooms        目前存在的動態房間
POST /dashboard/guilds/{id}/dynamic-voice/rooms/clear  body `{channel_ids}`，刪除其中沒人的房間

房間紀錄在資料庫，房間本身在 Discord：清單以資料庫的紀錄為準，逐筆對照 Discord 的實際狀態。
"""

import logging
from dataclasses import dataclass

import discord
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from starlib import sqldb

from .access import on_guild_async, require_guild_access
from .db import run_db

log = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard")


@dataclass(frozen=True)
class _Record:
    """不綁 session 的房間紀錄（run_db 結束後 ORM instance 會過期）"""

    channel_id: int
    creator_id: int


def _load_records(guild_id: int) -> list[_Record]:
    return [_Record(r.channel_id, r.creator_id) for r in sqldb.get_dynamic_voice_rooms_fresh(guild_id)]


async def _resolve_channel(guild: discord.Guild, channel_id: int) -> discord.abc.GuildChannel | None:
    """取得頻道；確定不存在回 None。

    bot 開房後立刻寫紀錄，但新頻道要等 gateway 事件才進 guild 快取，這段期間 get_channel 回 None，
    所以快取沒有時再向 Discord 確認一次，只有 NotFound 才算不存在。

    Raises:
        discord.HTTPException: 無法確認頻道是否存在（NotFound 以外的錯誤）。
    """
    channel = guild.get_channel(channel_id)
    if channel is not None:
        return channel
    try:
        return await guild.fetch_channel(channel_id)
    except discord.NotFound:
        return None


# ====== 清單 ======
def _creator(guild: discord.Guild, creator_id: int) -> dict | None:
    member = guild.get_member(creator_id)
    if member is None:
        return None
    return {"name": member.display_name, "avatar_url": member.display_avatar.url}


@router.get("/guilds/{guild_id}/dynamic-voice/rooms")
async def get_rooms(guild_id: int = Depends(require_guild_access)):
    records = await run_db(lambda: _load_records(guild_id))

    async def _read(guild: discord.Guild) -> tuple[list[dict], list[int]]:
        rooms: list[dict] = []
        gone: list[int] = []
        for record in records:
            try:
                channel = await _resolve_channel(guild, record.channel_id)
            except discord.HTTPException:
                # 無法確認就不動它：既不顯示也不刪紀錄，下次載入再試
                log.warning("Cannot resolve dynamic voice channel", extra={"channel_id": record.channel_id}, exc_info=True)
                continue
            if channel is None:
                gone.append(record.channel_id)
                continue
            rooms.append(
                {
                    "id": str(channel.id),
                    "name": channel.name,
                    "member_count": len(channel.members),  # pyright: ignore[reportAttributeAccessIssue]
                    "created_at": channel.created_at.isoformat(),
                    "creator": _creator(guild, record.creator_id),
                }
            )
        rooms.sort(key=lambda r: r["created_at"])
        return rooms, gone

    rooms, gone = await on_guild_async(guild_id, _read)
    if gone:
        # 頻道已被刪除的殘留紀錄自動清掉，不顯示給管理員
        await run_db(lambda: sqldb.batch_remove_dynamic_voice(gone))
    return {"rooms": rooms}


# ====== 清除空房 ======
class ClearBody(BaseModel):
    #: Discord ID 用字串
    channel_ids: list[int] = Field(min_length=1)


async def _clear_one(guild: discord.Guild, channel_id: int) -> dict:
    """在 bot 的事件迴圈上清除一間房，回傳這筆的結果。刪除前重新確認房內沒人。"""
    try:
        channel = await _resolve_channel(guild, channel_id)
    except discord.HTTPException as e:
        return {"id": str(channel_id), "name": None, "status": "failed", "reason": e.text or str(e)}
    if channel is None:
        return {"id": str(channel_id), "name": None, "status": "cleared"}

    result = {"id": str(channel_id), "name": channel.name}
    if channel.members:  # pyright: ignore[reportAttributeAccessIssue]
        return {**result, "status": "skipped_occupied"}
    try:
        await channel.delete(reason="動態語音：管理員從後台清除")
    except discord.NotFound:
        pass  # 已經不在了，視為清除成功
    except discord.Forbidden:
        return {**result, "status": "failed", "reason": "bot 沒有刪除這個頻道的權限"}
    except discord.HTTPException as e:
        return {**result, "status": "failed", "reason": e.text or str(e)}
    return {**result, "status": "cleared"}


@router.post("/guilds/{guild_id}/dynamic-voice/rooms/clear")
async def clear_rooms(body: ClearBody, guild_id: int = Depends(require_guild_access)):
    requested = list(dict.fromkeys(body.channel_ids))
    owned = {r.channel_id for r in await run_db(lambda: _load_records(guild_id))}
    valid = [cid for cid in requested if cid in owned]

    async def _clear(guild: discord.Guild) -> dict[int, dict]:
        return {cid: await _clear_one(guild, cid) for cid in valid}

    cleared_by_id = await on_guild_async(guild_id, _clear) if valid else {}
    cleared_ids = [cid for cid, r in cleared_by_id.items() if r["status"] == "cleared"]
    if cleared_ids:
        await run_db(lambda: sqldb.batch_remove_dynamic_voice(cleared_ids))

    # 有人的房間一律逐筆回 skipped_occupied，整個請求仍是 200
    results = [
        cleared_by_id[cid] if cid in cleared_by_id else {"id": str(cid), "name": None, "status": "failed", "reason": "不是動態房間"}
        for cid in requested
    ]
    return {"results": results}
