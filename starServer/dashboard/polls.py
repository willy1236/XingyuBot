"""投票區塊：
GET /dashboard/guilds/{id}/polls?all=&page=   投票清單（進行中全部在第 1 頁頂端，已結算每頁 20 筆）
GET /dashboard/guilds/{id}/polls/{poll_id}    單一投票的設定、依可見範圍給的票數與投票明細

權限一律經 `require_section(Section.POLLS)`。資料以資料庫為準，Discord 只用來補成員、頻道、身分組名稱，
以及 bot 在投票頻道缺少的權限（`PollView.missing_permissions`）。能看到什麼由 `starlib.polls` 決定。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

import discord
from fastapi import APIRouter, Depends, Query

from starDiscord.uiElement.view import MESSAGE_FAILURE_TEXT, PollView
from starlib import sclient, sqldb
from starlib.polls import PollResults, can_manage, results_mode, viewer_role, visibility
from starlib.utils import nowtz

from .access import Section, on_guild, on_guild_async, require_section
from .db import run_db
from .errors import DashboardError
from .session import SessionInfo, require_session

router = APIRouter(prefix="/dashboard")

PAGE_SIZE = 20
#: 預設只列最近這段時間內建立的投票，`all=true` 才列全部；進行中的投票不受限制
RECENT_DAYS = 90


@dataclass(frozen=True)
class _Row:
    """不綁 session 的投票資料（run_db 結束後 ORM instance 會過期）"""

    id: int
    title: str
    guild_id: int
    creator_id: int
    channel_id: int | None
    message_id: int | None
    created_at: datetime
    end_at: datetime | None
    deadline: datetime | None
    show_name: bool
    check_results_in_advance: bool
    results_only_initiator: bool
    number_of_user_votes: int
    message_failure: str | None
    voter_count: int = 0


def _to_row(poll, voter_count: int = 0) -> _Row:
    return _Row(
        id=poll.poll_id,
        title=poll.title,
        guild_id=poll.guild_id,
        creator_id=poll.creator_id,
        channel_id=poll.channel_id,
        message_id=poll.message_id,
        created_at=poll.created_at,
        end_at=poll.end_at,
        deadline=poll.deadline,
        show_name=bool(poll.show_name),
        check_results_in_advance=bool(poll.check_results_in_advance),
        results_only_initiator=bool(poll.results_only_initiator),
        number_of_user_votes=poll.number_of_user_votes or 1,
        message_failure=poll.message_failure,
        voter_count=voter_count,
    )


def _load_list(guild_id: int, since: datetime | None, page: int) -> tuple[list[_Row], list[_Row], bool]:
    active = sqldb.list_active_guild_polls(guild_id)
    # 多讀一筆判斷有沒有下一頁
    ended = sqldb.list_guild_polls(guild_id, since, (page - 1) * PAGE_SIZE, PAGE_SIZE + 1)
    has_next = len(ended) > PAGE_SIZE
    ended = ended[:PAGE_SIZE]
    shown = active if page == 1 else []
    counts = sqldb.count_poll_voters(shown + ended)
    return (
        [_to_row(p, counts.get(p.poll_id, 0)) for p in shown],
        [_to_row(p, counts.get(p.poll_id, 0)) for p in ended],
        has_next,
    )


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _member_name(guild: discord.Guild, user_id: int) -> str | None:
    """只回本伺服器成員的顯示名稱。已離開的成員即使 bot 在其他伺服器仍看得到使用者，也不回名稱，讓前端標成已離開。"""
    member = guild.get_member(user_id)
    return member.display_name if member is not None else None


def _channel_info(guild: discord.Guild, channel_id: int | None) -> dict:
    """channel_state：ok｜unknown（channel_id 為 null）｜missing（頻道已不存在）。

    channel_name 與 missing_permissions（bot 缺少的權限名稱，齊全為空 list）只在 ok 時有值。
    """
    if channel_id is None:
        return {"channel_state": "unknown", "channel_name": None, "missing_permissions": None}
    channel = guild.get_channel_or_thread(channel_id)
    if channel is None:
        return {"channel_state": "missing", "channel_name": None, "missing_permissions": None}
    return {
        "channel_state": "ok",
        "channel_name": channel.name,
        "missing_permissions": PollView.missing_permissions(channel, channel.permissions_for(guild.me)),
    }


def _summary(guild_id: int, row: _Row, guild: discord.Guild) -> dict:
    channel = _channel_info(guild, row.channel_id)
    message_url = None
    if channel["channel_state"] == "ok" and row.message_id is not None:
        message_url = f"https://discord.com/channels/{guild_id}/{row.channel_id}/{row.message_id}"
    return {
        "id": row.id,
        "title": row.title,
        "status": "active" if row.end_at is None else "ended",
        "voter_count": row.voter_count,
        "creator_id": str(row.creator_id),
        "creator_name": _member_name(guild, row.creator_id),
        "channel_id": str(row.channel_id) if row.channel_id is not None else None,
        **channel,
        "message_url": message_url,
        "created_at": _iso(row.created_at),
        "ended_at": _iso(row.end_at),
        "deadline": _iso(row.deadline),
    }


@router.get("/guilds/{guild_id}/polls")
async def list_polls(
    all: bool = False,
    page: int = Query(1, ge=1),
    guild_id: int = Depends(require_section(Section.POLLS)),
):
    since = None if all else nowtz() - timedelta(days=RECENT_DAYS)
    active, ended, has_next = await run_db(lambda: _load_list(guild_id, since, page))
    rows = await on_guild(guild_id, lambda guild: [_summary(guild_id, r, guild) for r in active + ended])
    return {"polls": rows, "page": page, "has_next": has_next, "all": all, "recent_days": RECENT_DAYS}


def _load_detail(guild_id: int, poll_id: int):
    poll = sqldb.get_poll_fresh(poll_id)
    # 其他伺服器的投票一律當作不存在，不洩漏它是否存在
    if poll is None or poll.guild_id != guild_id:
        return None
    results = PollResults.load(sqldb, poll)
    roles = [(r.role_id, r.is_only_role, r.role_magnification) for r in sqldb.get_poll_role(poll_id)]
    return _to_row(poll, results.voter_count), poll, results, roles


@router.get("/guilds/{guild_id}/polls/{poll_id:int}")
async def get_poll(
    poll_id: int,
    guild_id: int = Depends(require_section(Section.POLLS)),
    info: SessionInfo = Depends(require_session),
):
    loaded = await run_db(lambda: _load_detail(guild_id, poll_id))
    if loaded is None:
        raise DashboardError(404, "poll_not_found")
    row, poll, results, roles = loaded
    user_id = int(info.discord_user_id)

    async def _read(guild: discord.Guild) -> dict:
        is_owner = await sclient.bot.is_owner(discord.Object(user_id))  # type: ignore[arg-type]
        role = viewer_role(
            poll, user_id, is_owner=is_owner, creator_in_guild=guild.get_member(row.creator_id) is not None
        )
        show_counts, show_names = visibility(poll, role)

        def role_name(role_id: int) -> str | None:
            r = guild.get_role(role_id)
            return r.name if r is not None else None

        votes = None
        if show_names:
            votes = []
            for v in results.votes:
                votes.append(
                    {
                        "user_id": str(v.user_id),
                        "name": _member_name(guild, v.user_id),
                        "left": guild.get_member(v.user_id) is None,
                        "option_id": v.option_id,
                        "weight": v.weight,
                        "voted_at": _iso(v.voted_at),
                    }
                )
        failure = row.message_failure
        return {
            **_summary(guild_id, row, guild),
            "show_name": row.show_name,
            "results_visibility": results_mode(poll),
            "number_of_user_votes": row.number_of_user_votes,
            "only_roles": [{"id": str(rid), "name": role_name(rid)} for rid, only, _ in roles if only],
            "role_weights": [
                {"id": str(rid), "name": role_name(rid), "weight": weight} for rid, _, weight in roles if weight > 1
            ],
            "options": [{"option_id": o.option_id, "name": o.name} for o in results.options],
            "viewer": {"role": role, "can_manage": can_manage(role)},
            "counts": [{"option_id": o.option_id, "name": o.name, "count": o.count} for o in results.options]
            if show_counts
            else None,
            "votes": votes,
            "message_failure": failure,
            "message_failure_text": MESSAGE_FAILURE_TEXT.get(failure) if failure else None,
        }

    return await on_guild_async(guild_id, _read)
