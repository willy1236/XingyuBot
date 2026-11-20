"""伺服器語音時數排名：管理頁的排行榜、個人區的名次與成員看的排行頁共用同一套算法。

GET /dashboard/personal/voice-ranking/{guild_id}?offset=&limit=
    `{guild_name, total, items:[{rank, member, minutes, mine}], mine:[{rank, member, minutes}]}`
    可見的 Discord 任一個是該伺服器成員才能看，否則 403 not_member；bot 不在該伺服器回 404 bot_not_in_guild。

時數＝資料庫加上尚未存檔的分鐘（`task.voice_times`），由多到少、同分依 Discord ID，名次就是排序後的位置。
本模組的函式都在 bot 的事件迴圈上呼叫而且整段沒有 await：`add_voice_time`、`save_voice_time` 與它們跑在同一個 loop，
讀 DB 與取快照之間不會被插入存檔，不會重複計算或漏算。刻意直接讀 DB（不經 run_db），與 giveaways.py 同一個例外。
"""

from datetime import timedelta

import discord
from fastapi import APIRouter, Depends, Query

from starDiscord.cmds import task as voice_task
from starlib import sqldb

from .access import on_guild
from .errors import DashboardError
from .personal import PersonalScope, require_personal

router = APIRouter(prefix="/dashboard")

PAGE_SIZE = 50


def ranking(guild_id: int) -> list[tuple[int, timedelta]]:
    """伺服器內所有成員的 (Discord ID, 總時數)，依名次排序。"""
    totals: dict[int, timedelta] = {
        r.discord_id: r.total_minute for r in sqldb.get_voice_time_leaderboard(guild_id, None)
    }
    for uid, delta in voice_task.voice_times.get(guild_id, {}).items():
        totals[uid] = totals.get(uid, timedelta()) + delta
    return sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))


def minutes(total: timedelta) -> int:
    return int(total.total_seconds() // 60)


def member_json(guild: discord.Guild, uid: int) -> dict:
    """排行上的成員；已離開的成員 left 為 true，名稱與頭像為 null。"""
    member = guild.get_member(uid)
    return {
        "id": str(uid),
        "name": member.display_name if member is not None else None,
        "avatar_url": member.display_avatar.url if member is not None else None,
        "left": member is None,
    }


def is_member(guild: discord.Guild, discord_ids: list[int]) -> bool:
    return any(guild.get_member(i) is not None for i in discord_ids)


@router.get("/personal/voice-ranking/{guild_id}")
async def voice_ranking(
    guild_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(PAGE_SIZE, ge=1, le=PAGE_SIZE),
    scope: PersonalScope = Depends(require_personal()),
):
    mine = set(scope.discord_ids)

    def _read(guild: discord.Guild) -> dict:
        if not is_member(guild, scope.discord_ids):
            raise DashboardError(403, "not_member")
        ranked = ranking(guild.id)

        def row(index: int, uid: int, total: timedelta) -> dict:
            return {"rank": index + 1, "member": member_json(guild, uid), "minutes": minutes(total)}

        return {
            "guild_name": guild.name,
            "total": len(ranked),
            "items": [
                {**row(offset + i, uid, total), "mine": uid in mine}
                for i, (uid, total) in enumerate(ranked[offset : offset + limit])
            ],
            "mine": [row(i, uid, total) for i, (uid, total) in enumerate(ranked) if uid in mine],
        }

    return await on_guild(guild_id, _read)
