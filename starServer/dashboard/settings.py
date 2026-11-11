"""基本設定區塊：
GET /dashboard/guilds/{id}/settings   `{voice_time_counter, leaderboard:[{member, minutes}]}`
PUT /dashboard/guilds/{id}/settings   body `{values, original}`，回傳同 GET

權限一律經 `require_section(Section.SETTINGS)`（Manage Server）。修改用條件式寫入（WHERE 帶原始值），
後到的一定被擋下並回 409 conflict。`voice_time_counter` 在資料庫可為 NULL 或沒有設定列，一律視為 False。
"""

from datetime import timedelta

import discord
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from starDiscord.cmds import task as voice_task
from starlib import sqldb
from starlib.exceptions import DataExistError

from .access import Section, on_guild, require_section
from .conflict import Conflict
from .db import run_db
from .errors import DashboardError

router = APIRouter(prefix="/dashboard")

LEADERBOARD_SIZE = 20


def _current_values(guild_id: int) -> dict[str, bool]:
    """資料庫目前的設定（欄位同 original）；沒有設定列也是 False 的有效設定，回傳值一定存在。同步 DB，要經 run_db。"""
    row = sqldb.get_guild_setting_fresh(guild_id)
    return {"voice_time_counter": bool(row.voice_time_counter) if row is not None else False}


def _leaderboard(guild: discord.Guild) -> list[dict]:
    """排行榜前 N 名：資料庫的時數加上尚未存檔的分鐘（`task.voice_times`）。

    在 bot 的事件迴圈上呼叫，而且整段沒有 await：`add_voice_time`、`save_voice_time` 與它跑在同一個 loop，
    讀 DB 與取快照之間不會被插入存檔，不會重複計算或漏算。刻意直接讀 DB（不經 run_db），與 giveaways.py 同一個例外。
    """
    pending = dict(voice_task.voice_times.get(guild.id, {}))
    totals: dict[int, timedelta] = {r.discord_id: r.total_minute for r in sqldb.get_voice_time_leaderboard(guild.id, LEADERBOARD_SIZE)}
    # 有未存檔分鐘的成員可能不在資料庫前 N 名，補讀他們的資料庫時數再合併
    outside = [uid for uid in pending if uid not in totals]
    if outside:
        totals.update({uid: r.total_minute for uid, r in sqldb.get_voice_times(outside, guild.id).items()})
    for uid, delta in pending.items():
        totals[uid] = totals.get(uid, timedelta()) + delta

    ranked = sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))[:LEADERBOARD_SIZE]
    rows = []
    for uid, total in ranked:
        member = guild.get_member(uid)
        rows.append(
            {
                "member": {
                    "id": str(uid),
                    "name": member.display_name if member is not None else None,
                    "avatar_url": member.display_avatar.url if member is not None else None,
                    "left": member is None,
                },
                "minutes": int(total.total_seconds() // 60),
            }
        )
    return rows


async def _response(guild_id: int) -> dict:
    values = await run_db(lambda: _current_values(guild_id))
    return {**values, "leaderboard": await on_guild(guild_id, _leaderboard)}


@router.get("/guilds/{guild_id}/settings")
async def get_settings(guild_id: int = Depends(require_section(Section.SETTINGS))):
    return await _response(guild_id)


class SettingValues(BaseModel):
    voice_time_counter: bool


class PutBody(BaseModel):
    values: SettingValues
    #: 打開表單時看到的值
    original: SettingValues


@router.put("/guilds/{guild_id}/settings")
async def put_settings(body: PutBody, guild_id: int = Depends(require_section(Section.SETTINGS))):
    values = {"voice_time_counter": body.values.voice_time_counter}
    original = {"voice_time_counter": body.original.voice_time_counter}

    def _write() -> None:
        def conflict() -> DashboardError:
            return Conflict(_current_values(guild_id)).to_error()

        if sqldb.get_guild_setting_fresh(guild_id) is None:
            # 沒有設定列等同 False：original 也是 False 才能新增，否則是別人改過
            if original["voice_time_counter"]:
                raise conflict()
            try:
                sqldb.insert_guild_setting(guild_id, values)
            except DataExistError:
                raise conflict() from None
        elif sqldb.update_guild_setting_if(guild_id, original, values) == 0:
            raise conflict()
        sqldb.refresh_voice_time_counter_cache()

    await run_db(_write)
    return await _response(guild_id)
