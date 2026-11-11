"""警告區塊（紀錄清單與成員查詢）：
GET /dashboard/guilds/{id}/warnings?member=&kind=&page=       本伺服器發出的紀錄，由新到舊，每頁 50 筆
GET /dashboard/guilds/{id}/warnings/members/{user_id}         成員的跨群紀錄（只能查目前在本伺服器的成員）
GET /dashboard/guilds/{id}/warnings/member-search?q=          以名稱或 ID 搜尋本伺服器成員，最多 25 位

權限一律經 `require_section(Section.WARNINGS, "view")`。紀錄以資料庫為準，Discord 只用來補名稱與頭像。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

import discord
from fastapi import APIRouter, Depends, Query

from starlib import sclient, sqldb
from starlib.database import UserModerate, WarningType

from .access import Section, on_guild, require_section
from .db import run_db
from .errors import DashboardError

router = APIRouter(prefix="/dashboard")

PAGE_SIZE = 50
SEARCH_LIMIT = 25

_KIND_NAMES = {
    "warning": WarningType.Warning,
    "timeout": WarningType.Timeout,
    "kick": WarningType.Kick,
    "ban": WarningType.Ban,
}
_KIND_KEYS = {v: k for k, v in _KIND_NAMES.items()}


@dataclass(frozen=True)
class _Row:
    """不綁 session 的紀錄資料（run_db 結束後 ORM instance 會過期）"""

    warning_id: int
    discord_id: int
    moderate_type: WarningType
    moderate_user: int
    create_guild: int
    create_time: datetime
    reason: str | None
    last_time: timedelta | None
    guild_only: bool
    officially_given: bool


def _to_row(w: UserModerate) -> _Row:
    return _Row(
        warning_id=w.warning_id,
        discord_id=w.discord_id,
        moderate_type=WarningType(w.moderate_type),
        moderate_user=w.moderate_user,
        create_guild=w.create_guild,
        create_time=w.create_time,
        reason=w.reason,
        last_time=w.last_time,
        guild_only=bool(w.guild_only),
        officially_given=bool(w.officially_given),
    )


def _as_record(row: _Row) -> UserModerate:
    """還原成未綁 session 的 UserModerate，給 `embed()` 產生與 `/warning get` 相同的警告單。"""
    return UserModerate(
        warning_id=row.warning_id,
        discord_id=row.discord_id,
        moderate_type=row.moderate_type,
        moderate_user=row.moderate_user,
        create_guild=row.create_guild,
        create_time=row.create_time,
        reason=row.reason,
        last_time=row.last_time,
        guild_only=row.guild_only,
        officially_given=row.officially_given,
    )


def _person(guild: discord.Guild, user_id: int) -> dict:
    """本伺服器成員回名稱與頭像；已離開的成員 name 為 None、left 為 True，前端顯示「已離開的成員」。"""
    member = guild.get_member(user_id)
    return {
        "id": str(user_id),
        "name": member.display_name if member is not None else None,
        "avatar_url": member.display_avatar.url if member is not None else None,
        "left": member is None,
    }


def _item(guild: discord.Guild, row: _Row) -> dict:
    embed = _as_record(row).embed(sclient.bot)
    return {
        "id": row.warning_id,
        "kind": _KIND_KEYS[row.moderate_type],
        "target": _person(guild, row.discord_id),
        "moderator": _person(guild, row.moderate_user),
        "reason": row.reason,
        "created_at": row.create_time.isoformat(),
        "duration_seconds": int(row.last_time.total_seconds()) if row.last_time is not None else None,
        "cross_guild": not row.guild_only,
        "this_guild": row.create_guild == guild.id,
        "sheet": {"title": embed.author.name if embed.author else embed.title, "description": embed.description},
    }


def _parse_user_id(value: str | None, field: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        raise DashboardError(
            400, "invalid_request", fields=[{"path": field, "reason": "必須是 Discord 使用者 ID"}]
        ) from None


@router.get("/guilds/{guild_id}/warnings")
async def list_warnings(
    member: str | None = None,
    kind: str | None = None,
    page: int = Query(1, ge=1),
    guild_id: int = Depends(require_section(Section.WARNINGS)),
):
    member_id = _parse_user_id(member, "member")
    kind_value = None
    if kind:
        if kind not in _KIND_NAMES:
            raise DashboardError(400, "invalid_request", fields=[{"path": "kind", "reason": "不是有效的種類"}])
        kind_value = _KIND_NAMES[kind]

    def _load() -> tuple[list[_Row], int]:
        rows, total = sqldb.list_guild_warnings(guild_id, member_id, kind_value, (page - 1) * PAGE_SIZE, PAGE_SIZE)
        return [_to_row(w) for w in rows], total

    rows, total = await run_db(_load)
    items = await on_guild(guild_id, lambda guild: [_item(guild, r) for r in rows])
    return {
        "warnings": items,
        "page": page,
        "page_size": PAGE_SIZE,
        "total": total,
        "has_next": page * PAGE_SIZE < total,
    }


@router.get("/guilds/{guild_id}/warnings/member-search")
async def search_members(
    q: str = Query("", max_length=100), guild_id: int = Depends(require_section(Section.WARNINGS))
):
    text = q.strip().lower()

    def _search(guild: discord.Guild) -> list[dict]:
        if not text:
            return []
        found = []
        for m in guild.members:
            if (
                text.isdigit()
                and str(m.id) == text
                or any(text in (n or "").lower() for n in (m.name, m.display_name, getattr(m, "global_name", None)))
            ):
                found.append(m)
        found.sort(key=lambda m: m.display_name.lower())
        return [
            {"id": str(m.id), "name": m.display_name, "username": m.name, "avatar_url": m.display_avatar.url}
            for m in found[:SEARCH_LIMIT]
        ]

    return {"members": await on_guild(guild_id, _search)}


@router.get("/guilds/{guild_id}/warnings/members/{user_id}")
async def member_records(user_id: int, guild_id: int = Depends(require_section(Section.WARNINGS))):
    """成員在所有伺服器存入跨群系統的紀錄，加上本伺服器只在本伺服器的紀錄（同 `/warning list`）。"""
    person = await on_guild(guild_id, lambda guild: _person(guild, user_id))
    if person["left"]:
        raise DashboardError(400, "not_member")

    def _load() -> list[_Row]:
        rows = [_to_row(w) for w in sqldb.get_warnings(user_id, guild_id)]
        return sorted(rows, key=lambda r: (r.create_time, r.warning_id), reverse=True)

    rows = await run_db(_load)
    items = await on_guild(guild_id, lambda guild: [_item(guild, r) for r in rows])
    return {"member": person, "warnings": items}
