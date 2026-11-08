"""POST /dashboard/guilds/{id}/notifies/test：用已存的設定發送一則測試通知。

內容與預覽相同（build_sample），前面加測試標示；用 AllowedMentions.none()，身分組與本人都不會被通知。
1 分鐘共用冷卻，發送失敗不計入冷卻。定時通知不提供測試。
"""

from typing import Literal

import discord
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from starlib import sqldb

from .access import on_guild_async, require_guild_access
from .conflict import Conflict
from .db import run_db
from .errors import DashboardError
from .notify_cooldown import COOLDOWN_SECONDS, acquire, commit, cooldown_key, release
from .notify_fields import NotifySpec, parse_key
from .notify_input import field_names
from .samples import build_sample
from .session import SessionInfo, require_session
from .validity import channel_invalid_reason

router = APIRouter(prefix="/dashboard")

TEST_LABEL = "【測試通知】"


class SendTestBody(BaseModel):
    kind: Literal["channel", "community"]
    notify_type: str
    #: 社群推播的對象帳號
    account_id: str | None = None


def _load_values(guild_id: int, spec: NotifySpec, account_id: str | None) -> dict[str, int | str | None] | None:
    """已存的設定（只含該種類用得到的欄位）；不存在回 None。"""
    if spec.kind == "channel":
        row = sqldb.get_notify_channel_fresh(guild_id, spec.channel_type)
    else:
        assert account_id is not None
        row = sqldb.get_notify_community_fresh(spec.community_type, account_id, guild_id)
    if row is None:
        return None
    return {name: getattr(row, name) for name in field_names(spec)}


async def _fetch_member(guild: discord.Guild, user_id: int) -> discord.Member | None:
    if (member := guild.get_member(user_id)) is not None:
        return member
    try:
        return await guild.fetch_member(user_id)
    except discord.HTTPException:
        return None


def _failure(reason: str) -> DashboardError:
    return DashboardError(502, "send_failed", reason=reason)


@router.post("/guilds/{guild_id}/notifies/test")
async def send_test_notify(body: SendTestBody, guild_id: int = Depends(require_guild_access), info: SessionInfo = Depends(require_session)):
    try:
        spec = parse_key(body.notify_type)
    except KeyError:
        raise DashboardError(400, "invalid_request") from None
    if spec.kind != body.kind or (spec.kind == "community" and not body.account_id):
        raise DashboardError(400, "invalid_request")
    if spec.scheduled:
        raise DashboardError(400, "scheduled_not_testable")

    account_id = body.account_id if spec.kind == "community" else None
    values = await run_db(lambda: _load_values(guild_id, spec, account_id))
    if values is None:
        raise Conflict(None).to_error()

    key = cooldown_key(guild_id, spec.key, account_id)
    acquire(key)
    try:
        await on_guild_async(guild_id, lambda guild: _send(guild, spec, values, int(info.discord_user_id), key))
    except BaseException:
        release(key)
        raise
    return {"ok": True, "cooldown": COOLDOWN_SECONDS}


async def _send(guild: discord.Guild, spec: NotifySpec, values: dict, user_id: int, key: str) -> None:
    """在 bot 的事件迴圈上發送；送出後立刻 commit 冷卻，中間沒有 await，web 端取消請求也不會漏計。"""
    channel_id = values["channel_id"]
    if (reason := channel_invalid_reason(guild, channel_id, spec.scheduled)) is not None:  # pyright: ignore[reportArgumentType]
        raise _failure(reason)
    channel = guild.get_channel(channel_id)  # pyright: ignore[reportArgumentType]

    member = await _fetch_member(guild, user_id)
    str_values = {k: None if v is None else str(v) for k, v in values.items()}
    sample = build_sample(spec.key, str_values, member=member, guild=guild)
    content = f"{TEST_LABEL}\n{sample.content}" if sample.content else TEST_LABEL
    try:
        await channel.send(content, embeds=sample.embeds, allowed_mentions=discord.AllowedMentions.none())
    except discord.Forbidden:
        raise _failure("bot 沒有在該頻道發訊息的權限") from None
    except discord.HTTPException as e:
        raise _failure(f"Discord 回傳錯誤：{e.text or e.status}") from None
    commit(key)
