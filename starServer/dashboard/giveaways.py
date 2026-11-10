"""抽獎區塊：
GET /dashboard/guilds/{id}/giveaways?all=&page=   抽獎清單（進行中全部在第 1 頁頂端，已結束每頁 20 筆）
GET /dashboard/guilds/{id}/giveaways/{giveaway_id}  單一抽獎的詳情、參加者與中獎者
POST /dashboard/guilds/{id}/giveaways/{giveaway_id}/end     提前結束（body 無）
POST /dashboard/guilds/{id}/giveaways/{giveaway_id}/redraw  重抽，body `{winner_user_id?}`，未指定為整批重抽

權限一律經 `require_section(Section.GIVEAWAYS)`。資料以資料庫為準，Discord 只用來補成員名稱與頻道名稱。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

import discord
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from starDiscord.uiElement.view import GiveawayOutcome, GiveawayView
from starlib import sclient, sqldb
from starlib.utils import nowtz

from .access import Section, on_guild, on_guild_async, require_section
from .db import run_db
from .errors import DashboardError

router = APIRouter(prefix="/dashboard")

PAGE_SIZE = 20
#: 預設只列最近這段時間內建立的抽獎，`all=true` 才列全部；進行中的抽獎不受限制
RECENT_DAYS = 90


@dataclass(frozen=True)
class _Row:
    """不綁 session 的抽獎資料（run_db 結束後 ORM instance 會過期）"""

    id: int
    channel_id: int
    message_id: int | None
    creator_id: int
    prize_name: str
    description: str | None
    winner_count: int
    redraw_count: int
    created_at: datetime
    end_at: datetime | None
    deadline: datetime
    is_on: bool
    participant_count: int = 0


def _to_row(giveaway, participant_count: int = 0) -> _Row:
    return _Row(
        id=giveaway.id,
        channel_id=giveaway.channel_id,
        message_id=giveaway.message_id,
        creator_id=giveaway.creator_id,
        prize_name=giveaway.prize_name,
        description=giveaway.description,
        winner_count=giveaway.winner_count,
        redraw_count=giveaway.redraw_count or 0,
        created_at=giveaway.created_at,
        end_at=giveaway.end_at,
        deadline=giveaway.deadline,
        is_on=giveaway.is_on,
        participant_count=participant_count,
    )


def _load_list(guild_id: int, since: datetime | None, page: int) -> tuple[list[_Row], list[_Row], bool]:
    active = sqldb.list_active_guild_giveaways(guild_id)
    # 多讀一筆判斷有沒有下一頁
    ended = sqldb.list_guild_giveaways(guild_id, since, (page - 1) * PAGE_SIZE, PAGE_SIZE + 1)
    has_next = len(ended) > PAGE_SIZE
    ended = ended[:PAGE_SIZE]
    shown = active if page == 1 else []
    counts = sqldb.count_giveaway_users([g.id for g in shown + ended])
    return [_to_row(g, counts.get(g.id, 0)) for g in shown], [_to_row(g, counts.get(g.id, 0)) for g in ended], has_next


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _message_url(guild_id: int, row: _Row) -> str | None:
    if row.message_id is None:
        return None
    return f"https://discord.com/channels/{guild_id}/{row.channel_id}/{row.message_id}"


def _summary(guild_id: int, row: _Row) -> dict:
    return {
        "id": row.id,
        "prize_name": row.prize_name,
        "status": "active" if row.is_on else "ended",
        "winner_count": row.winner_count,
        "participant_count": row.participant_count,
        "redraw_count": row.redraw_count,
        "creator_id": str(row.creator_id),
        "channel_id": str(row.channel_id),
        "message_url": _message_url(guild_id, row),
        "created_at": _iso(row.created_at),
        # 進行中顯示預計開獎時間，已結束顯示實際結束時間
        "ends_at": _iso(row.deadline if row.is_on else row.end_at),
    }


@router.get("/guilds/{guild_id}/giveaways")
async def list_giveaways(
    all: bool = False,
    page: int = Query(1, ge=1),
    guild_id: int = Depends(require_section(Section.GIVEAWAYS)),
):
    since = None if all else nowtz() - timedelta(days=RECENT_DAYS)
    active, ended, has_next = await run_db(lambda: _load_list(guild_id, since, page))

    def _names(guild: discord.Guild) -> dict[int, str | None]:
        return {r.creator_id: _member_name(guild, r.creator_id) for r in active + ended}

    names = await on_guild(guild_id, _names)
    rows = []
    for r in active + ended:
        item = _summary(guild_id, r)
        item["creator_name"] = names.get(r.creator_id)
        rows.append(item)
    return {"giveaways": rows, "page": page, "has_next": has_next, "all": all, "recent_days": RECENT_DAYS}


def _member_name(guild: discord.Guild, user_id: int) -> str | None:
    member = guild.get_member(user_id)
    if member is not None:
        return member.display_name
    bot = sclient.bot
    user = bot.get_user(user_id) if bot is not None else None
    return user.name if user is not None else None


def _load_detail(guild_id: int, giveaway_id: int):
    giveaway = sqldb.get_giveaway_fresh(giveaway_id)
    # 其他伺服器的抽獎一律當作不存在，不洩漏它是否存在
    if giveaway is None or giveaway.guild_id != guild_id:
        return None
    users = sorted(sqldb.get_giveaway_users(giveaway_id), key=lambda u: u.join_at)
    participants = [(u.user_id, u.join_at, u.is_winner) for u in users]
    return _to_row(giveaway, len(participants)), participants


@router.get("/guilds/{guild_id}/giveaways/{giveaway_id}")
async def get_giveaway(giveaway_id: int, guild_id: int = Depends(require_section(Section.GIVEAWAYS))):
    loaded = await run_db(lambda: _load_detail(guild_id, giveaway_id))
    if loaded is None:
        raise DashboardError(404, "giveaway_not_found")
    row, participants = loaded

    def _read(guild: discord.Guild) -> dict:
        channel = guild.get_channel(row.channel_id)
        out = []
        for user_id, join_at, is_winner in participants:
            member = guild.get_member(user_id)
            out.append(
                {
                    "id": str(user_id),
                    "name": _member_name(guild, user_id),
                    "avatar_url": member.display_avatar.url if member is not None else None,
                    "left": member is None,
                    "joined_at": _iso(join_at),
                    "is_winner": is_winner,
                }
            )
        return {
            "channel_name": channel.name if channel is not None else None,
            "creator_name": _member_name(guild, row.creator_id),
            "participants": out,
        }

    info = await on_guild(guild_id, _read)
    return {
        **_summary(guild_id, row),
        "description": row.description,
        "channel_name": info["channel_name"],
        "creator_name": info["creator_name"],
        "participants": info["participants"],
        "winners": [p for p in info["participants"] if p["is_winner"]],
    }


# ====== 提前結束與重抽 ======
class RedrawBody(BaseModel):
    #: 指定要取消資格的中獎者（Discord ID，可送字串）；省略為整批重抽，已離開伺服器的中獎者也可以指定
    winner_user_id: int | None = None


def _result(outcome: GiveawayOutcome) -> dict:
    return {
        "status": outcome.status,
        "announce_failure": outcome.announce_failure,
        "announce_failure_text": outcome.announce_failure_text,
    }


async def _run(guild_id: int, giveaway_id: int, action) -> GiveawayOutcome:
    """在 bot 的事件迴圈上處理抽獎：每次都重新從資料庫讀，建立 GiveawayView 後交給 action。

    開獎與重抽的鎖、重讀 is_on 在 GiveawayView 內，與到期自動開獎、發起人按鈕、`/giveaway redraw` 共用同一套。
    """
    bot = sclient.bot

    async def _go(_guild: discord.Guild) -> GiveawayOutcome:
        giveaway = sqldb.get_giveaway_fresh(giveaway_id)
        # 其他伺服器的抽獎一律當作不存在
        if giveaway is None or giveaway.guild_id != guild_id:
            raise DashboardError(404, "giveaway_not_found")
        return await action(GiveawayView(giveaway, sqldb, bot))

    return await on_guild_async(guild_id, _go)


@router.post("/guilds/{guild_id}/giveaways/{giveaway_id}/end")
async def end_giveaway(giveaway_id: int, guild_id: int = Depends(require_section(Section.GIVEAWAYS, "end"))):
    """提前結束。抽獎已經結束（剛好到期或發起人剛按下）視為成功，status 為 already_ended。"""
    outcome = await _run(guild_id, giveaway_id, lambda view: view.finish())
    if outcome.status == "not_found":
        raise DashboardError(404, "giveaway_not_found")
    return _result(outcome)


@router.post("/guilds/{guild_id}/giveaways/{giveaway_id}/redraw")
async def redraw_giveaway(
    giveaway_id: int,
    body: RedrawBody | None = None,
    guild_id: int = Depends(require_section(Section.GIVEAWAYS, "redraw")),
):
    winner_id = body.winner_user_id if body else None
    outcome = await _run(guild_id, giveaway_id, lambda view: view.redraw(winner_id))
    match outcome.status:
        case "not_found":
            raise DashboardError(404, "giveaway_not_found")
        case "not_ended":
            raise DashboardError(409, "giveaway_not_ended")
        case "not_participant" | "not_winner":
            raise DashboardError(409, outcome.status)
    return _result(outcome)
