"""抽獎區塊：
GET /dashboard/guilds/{id}/giveaways?all=&page=   抽獎清單（進行中全部在第 1 頁頂端，已結束每頁 20 筆）
GET /dashboard/guilds/{id}/giveaways/{giveaway_id}  單一抽獎的詳情、參加者與中獎者

權限一律經 `require_section(Section.GIVEAWAYS)`。資料以資料庫為準，Discord 只用來補成員名稱與頻道名稱。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

import discord
from fastapi import APIRouter, Depends, Query

from starlib import sclient, sqldb
from starlib.utils import nowtz

from .access import Section, on_guild, require_section
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
