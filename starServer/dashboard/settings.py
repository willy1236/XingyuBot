"""基本設定區塊：
GET /dashboard/guilds/{id}/settings
    `{voice_time_counter, auto_timeout_enabled, auto_timeout_times, auto_timeout_seconds, permission_issues, leaderboard:[{member, minutes}]}`
PUT /dashboard/guilds/{id}/settings   body `{values, original}`，回傳同 GET

權限一律經 `require_section(Section.SETTINGS)`（Manage Server）。values、original 的欄位都可省略：只寫入、比對有帶的欄位，
values 裡的欄位 original 也要帶。修改用條件式寫入（WHERE 帶原始值），後到的一定被擋下並回 409 conflict。
資料庫欄位可為 NULL 或沒有設定列，一律視為預設值（語音時數統計關閉、自動禁言不啟用、3 次、10 分鐘），GET 回的是有效值。
"""

from dataclasses import asdict
from datetime import timedelta

import discord
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from starDiscord.cmds import task as voice_task
from starlib import sqldb
from starlib.auto_timeout import effective_setting, moderate_members_issue, valid_seconds, valid_times
from starlib.exceptions import DataExistError

from .access import Section, on_guild, require_section
from .conflict import Conflict
from .db import run_db
from .errors import DashboardError

router = APIRouter(prefix="/dashboard")

LEADERBOARD_SIZE = 20


#: 對外欄位 -> 資料表欄位
_COLUMNS = {
    "voice_time_counter": "voice_time_counter",
    "auto_timeout_enabled": "auto_timeout_enabled",
    "auto_timeout_times": "timeout_after_warning_times",
    "auto_timeout_seconds": "auto_timeout_seconds",
}


def _current_values(guild_id: int) -> dict[str, bool | int]:
    """資料庫目前的有效設定（欄位同 original，NULL 與沒有設定列已換成預設值）。同步 DB，要經 run_db。"""
    row = sqldb.get_guild_setting_fresh(guild_id)
    auto = effective_setting(row)
    return {
        "voice_time_counter": bool(row.voice_time_counter) if row is not None else False,
        "auto_timeout_enabled": auto.enabled,
        "auto_timeout_times": auto.times,
        "auto_timeout_seconds": auto.seconds,
    }


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

    def _read(guild: discord.Guild) -> tuple[list[dict], list[dict]]:
        issue = moderate_members_issue(guild)
        return _leaderboard(guild), [asdict(issue)] if issue else []

    leaderboard, issues = await on_guild(guild_id, _read)
    return {**values, "permission_issues": issues, "leaderboard": leaderboard}


@router.get("/guilds/{guild_id}/settings")
async def get_settings(guild_id: int = Depends(require_section(Section.SETTINGS))):
    return await _response(guild_id)


class SettingValues(BaseModel):
    voice_time_counter: bool | None = None
    auto_timeout_enabled: bool | None = None
    auto_timeout_times: int | None = None
    auto_timeout_seconds: int | None = None

    def provided(self) -> dict[str, bool | int]:
        """有帶的欄位（對外欄位名稱）"""
        return self.model_dump(exclude_none=True)


class PutBody(BaseModel):
    values: SettingValues
    #: 打開表單時看到的值
    original: SettingValues


def _validate(values: dict[str, bool | int], original: dict[str, bool | int]) -> None:
    if not values or not values.keys() <= original.keys():
        raise DashboardError(400, "invalid_request")
    if "auto_timeout_times" in values and not valid_times(values["auto_timeout_times"]):
        raise DashboardError(400, "invalid_request", field="auto_timeout_times")
    if "auto_timeout_seconds" in values and not valid_seconds(values["auto_timeout_seconds"]):
        raise DashboardError(400, "invalid_request", field="auto_timeout_seconds")


@router.put("/guilds/{guild_id}/settings")
async def put_settings(body: PutBody, guild_id: int = Depends(require_section(Section.SETTINGS))):
    values = body.values.provided()
    original = body.original.provided()
    _validate(values, original)
    db_values = {_COLUMNS[k]: v for k, v in values.items()}
    db_original = {_COLUMNS[k]: v for k, v in original.items()}

    def _write() -> None:
        def conflict() -> DashboardError:
            current = _current_values(guild_id)
            return Conflict({k: current[k] for k in original}).to_error()

        if sqldb.get_guild_setting_fresh(guild_id) is None:
            # 沒有設定列等同全部預設值：original 與目前（預設）值一致才能新增，否則是別人改過
            current = _current_values(guild_id)
            if any(current[k] != v for k, v in original.items()):
                raise conflict()
            try:
                sqldb.insert_guild_setting(guild_id, db_values)
            except DataExistError:
                raise conflict() from None
        elif sqldb.update_guild_setting_if(guild_id, db_original, db_values) == 0:
            raise conflict()
        sqldb.refresh_voice_time_counter_cache()

    await run_db(_write)
    return await _response(guild_id)
