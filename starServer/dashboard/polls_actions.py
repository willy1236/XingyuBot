"""投票區塊的寫入：
POST   /dashboard/guilds/{id}/polls/{poll_id}/end   結算（body 無）
DELETE /dashboard/guilds/{id}/polls/{poll_id}       刪除 Discord 訊息與全部資料（body 無）

只有發起人、bot owner，以及發起人不在伺服器時的管理員能操作，判斷交給 `starlib.polls.can_manage`。
結算一律經 `PollView.finish`，與按鈕、指令共用同一把鎖與流程。
"""

import discord
from apscheduler.jobstores.base import JobLookupError
from fastapi import APIRouter, Depends

from starDiscord.uiElement.view import MESSAGE_FAILURE_TEXT, PollView
from starlib import sclient, sqldb
from starlib.polls import can_manage, viewer_role

from .access import Section, on_guild_async, require_section
from .db import run_db
from .errors import DashboardError
from .session import SessionInfo, require_session

router = APIRouter(prefix="/dashboard")


def _result(status: str, message_failure: str | None) -> dict:
    return {
        "status": status,
        "message_failure": message_failure,
        "message_failure_text": MESSAGE_FAILURE_TEXT.get(message_failure) if message_failure else None,
    }


async def _require_manager(guild: discord.Guild, poll, user_id: int) -> None:
    is_owner = await sclient.bot.is_owner(discord.Object(user_id))  # type: ignore[arg-type, union-attr]
    role = viewer_role(poll, user_id, is_owner=is_owner, creator_in_guild=guild.get_member(poll.creator_id) is not None)
    if not can_manage(role):
        raise DashboardError(403, "not_poll_manager")


@router.post("/guilds/{guild_id}/polls/{poll_id:int}/end")
async def end_poll(
    poll_id: int,
    guild_id: int = Depends(require_section(Section.POLLS, "end")),
    info: SessionInfo = Depends(require_session),
):
    """結算。投票已結算（剛好被按鈕或其他來源結算）視為成功，status 為 already_ended。"""
    user_id = int(info.discord_user_id)
    bot = sclient.bot

    async def _go(guild: discord.Guild) -> dict:
        # 刻意例外：在 bot loop 上直接讀 DB（不經 run_db），才能與 PollView 共用同一把鎖與 bot thread 的 session。
        poll = sqldb.get_poll_fresh(poll_id)
        # 其他伺服器的投票一律當作不存在
        if poll is None or poll.guild_id != guild_id:
            raise DashboardError(404, "poll_not_found")
        await _require_manager(guild, poll, user_id)
        outcome = await PollView(poll, sqldb, bot).finish()
        if outcome.status == "not_found":
            raise DashboardError(404, "poll_not_found")
        return _result(outcome.status, outcome.message_failure)

    return await on_guild_async(guild_id, _go)


async def _delete_message(guild: discord.Guild, channel_id: int | None, message_id: int | None) -> str | None:
    """刪除投票訊息；回傳沒能刪除的原因代碼，成功或訊息本來就不在（含頻道已不存在）為 None。"""
    if channel_id is None or message_id is None:
        return "message_unknown"
    try:
        channel = guild.get_channel_or_thread(channel_id) or await sclient.bot.fetch_channel(channel_id)  # type: ignore[union-attr]
    except discord.NotFound:
        return None
    except discord.Forbidden:
        return "no_permission"
    except discord.HTTPException:
        return "failed"
    try:
        await channel.get_partial_message(message_id).delete()  # type: ignore[union-attr]
    except discord.NotFound:
        return None
    except discord.Forbidden:
        return "no_permission"
    except discord.HTTPException:
        return "failed"
    return None


@router.delete("/guilds/{guild_id}/polls/{poll_id:int}")
async def delete_poll(
    poll_id: int,
    guild_id: int = Depends(require_section(Section.POLLS, "delete")),
    info: SessionInfo = Depends(require_session),
):
    """刪除。先刪訊息再刪資料：資料刪除失敗回 500，重試時訊息 NotFound 視為成功。

    投票不存在（含已刪除、屬於其他伺服器）回 status 為 already_deleted。
    已註冊的 view 不停掉，留在 Discord 上的按鈕才會走到 callback 回「此投票已不存在」。
    """
    user_id = int(info.discord_user_id)

    async def _go(guild: discord.Guild) -> dict | None:
        # 刻意例外：在 bot loop 上直接讀 DB，與 end 同一個理由
        poll = sqldb.get_poll_fresh(poll_id)
        if poll is None or poll.guild_id != guild_id:
            return None
        await _require_manager(guild, poll, user_id)
        return _result("ok", await _delete_message(guild, poll.channel_id, poll.message_id))

    result = await on_guild_async(guild_id, _go)
    if result is None:
        return _result("already_deleted", None)
    await run_db(lambda: sqldb.delete_poll(poll_id))
    try:
        sclient.bot.scheduler.remove_job(f"poll_end_{poll_id}")  # type: ignore[union-attr]
    except JobLookupError:
        pass
    return result
