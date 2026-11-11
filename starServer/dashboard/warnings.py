"""警告區塊（紀錄清單與成員查詢）：
GET /dashboard/guilds/{id}/warnings?member=&kind=&page=       本伺服器發出的紀錄，由新到舊，每頁 50 筆
GET /dashboard/guilds/{id}/warnings/members/{user_id}         成員的跨群紀錄（只能查目前在本伺服器的成員）
GET /dashboard/guilds/{id}/warnings/member-search?q=          以名稱或 ID 搜尋本伺服器成員，最多 25 位
GET /dashboard/guilds/{id}/warnings/options                   可公告的文字頻道
POST /dashboard/guilds/{id}/warnings                          警告、禁言、踢出、停權，權限依種類
DELETE /dashboard/guilds/{id}/warnings/{warning_id}           移除本伺服器發出的紀錄，不連帶解除禁言或停權

讀取一律經 `require_section(Section.WARNINGS)`。紀錄以資料庫為準，Discord 只用來補名稱與頭像。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

import discord
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from starlib import sclient, sqldb
from starlib.database import UserModerate, WarningType
from starlib.moderation import MAX_TIMEOUT, AutoTimeoutResult, PunishResult, announcement, punish

from .access import Section, on_guild, on_guild_async, require_section
from .db import run_db
from .errors import DashboardError
from .session import SessionInfo, require_session
from .validity import channel_invalid_reason

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
            {
                "id": str(m.id),
                "name": m.display_name,
                "username": m.name,
                "avatar_url": m.display_avatar.url,
                "bot": bool(getattr(m, "bot", False)),
            }
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


MAX_REASON = 100
MIN_TIMEOUT_SECONDS = 60
#: 停權可選的刪訊息秒數，與 `/ban` 的選項一致；禁言是 0 到 7 天
BAN_DELETE_SECONDS = (0, 3600, 21600, 43200, 86400, 259200, 604800)
MAX_DELETE_SECONDS = int(MAX_TIMEOUT.total_seconds())
MAX_SNOWFLAKE = 2**63 - 1

#: 各種類要求的動作權限；請求 body 才知道種類，所以在 handler 內依序檢查
_KIND_ACTIONS = {"warning": "add", "timeout": "timeout", "kick": "kick", "ban": "ban"}
_KIND_PERMISSION = {k: require_section(Section.WARNINGS, a) for k, a in _KIND_ACTIONS.items()}
_REASON_REQUIRED = ("warning", "ban")
_MEMBER_ONLY = ("timeout", "kick")


@router.get("/guilds/{guild_id}/warnings/options")
async def punish_options(guild_id: int = Depends(require_section(Section.WARNINGS))):
    """可公告的文字頻道：bot 能檢視、發言與嵌入連結的頻道。"""

    def _channels(guild: discord.Guild) -> list[dict]:
        return [
            {"id": str(c.id), "name": c.name}
            for c in sorted(guild.text_channels, key=lambda c: (c.position, c.id))
            if channel_invalid_reason(guild, c.id, False) is None
        ]

    return {"channels": await on_guild(guild_id, _channels)}


class PunishBody(BaseModel):
    kind: str
    user_id: int | str
    reason: str | None = None
    cross_guild: bool = False
    duration_seconds: int | None = None
    delete_message_seconds: int | None = None
    announce_channel_id: int | str | None = None


def _field(path: str, reason: str) -> dict:
    return {"path": path, "reason": reason}


def _snowflake(value: int | str | None, path: str, errors: list[dict]) -> int | None:
    try:
        number = int(value)  # pyright: ignore[reportArgumentType]
    except TypeError, ValueError:
        errors.append(_field(path, "必須是 Discord ID"))
        return None
    if not 0 < number <= MAX_SNOWFLAKE:
        errors.append(_field(path, "必須是 Discord ID"))
        return None
    return number


def _validate(body: PunishBody) -> tuple[int, int | None, timedelta | None, int | None]:
    """回傳 (user_id, announce_channel_id, duration, delete_message_seconds)；不合規則丟 400 並附 fields。"""
    errors: list[dict] = []
    user_id = _snowflake(body.user_id, "user_id", errors)
    announce_id = None
    if body.announce_channel_id not in (None, ""):
        announce_id = _snowflake(body.announce_channel_id, "announce_channel_id", errors)

    reason = (body.reason or "").strip()
    if len(reason) > MAX_REASON:
        errors.append(_field("reason", f"原因不得超過 {MAX_REASON} 字"))
    if body.kind in _REASON_REQUIRED and not reason:
        errors.append(_field("reason", "必須填寫原因"))

    duration = None
    if body.kind == "timeout":
        seconds = body.duration_seconds
        if seconds is None or not MIN_TIMEOUT_SECONDS <= seconds <= MAX_DELETE_SECONDS:
            errors.append(_field("duration_seconds", "禁言時長必須在 1 分鐘到 7 天之間"))
        else:
            duration = timedelta(seconds=seconds)

    delete_seconds = None
    if body.kind in ("timeout", "ban") and body.delete_message_seconds:
        delete_seconds = body.delete_message_seconds
        if body.kind == "ban" and delete_seconds not in BAN_DELETE_SECONDS:
            errors.append(_field("delete_message_seconds", "不是有效的選項"))
        elif body.kind == "timeout" and not 0 <= delete_seconds <= MAX_DELETE_SECONDS:
            errors.append(_field("delete_message_seconds", "必須在 0 到 7 天之間"))

    if errors:
        raise DashboardError(400, "invalid_request", fields=errors)
    return user_id, announce_id, duration, delete_seconds  # pyright: ignore[reportReturnType]


async def _resolve_user(guild: discord.Guild, user_id: int, must_be_member: bool) -> discord.User | discord.Member:
    member = guild.get_member(user_id)
    if member is not None:
        return member
    if must_be_member:
        raise DashboardError(400, "not_member")
    try:
        return await sclient.bot.fetch_user(user_id)  # pyright: ignore[reportOptionalMemberAccess]
    except discord.HTTPException:
        raise DashboardError(400, "user_not_found") from None


def _auto_timeout(auto: AutoTimeoutResult | None) -> dict | None:
    if auto is None:
        return None
    return {
        "ok": auto.ok,
        "duration_seconds": int(auto.duration.total_seconds()) if auto.duration is not None else None,
        "error": auto.error,
    }


def _result(result: PunishResult) -> dict:
    return {
        "ok": result.ok,
        "error": result.error,
        "warning_id": result.warning_id,
        "already": result.already,
        "deleted_summary": result.deleted_summary,
        "auto_timeout": _auto_timeout(result.auto_timeout),
    }


async def _announce(guild: discord.Guild, channel_id: int, result: PunishResult, target, actor) -> str | None:
    """發送公告；失敗回原因，不影響已寫的紀錄。"""
    if (reason := channel_invalid_reason(guild, channel_id, False)) is not None:
        return reason
    try:
        await guild.get_channel(channel_id).send(**announcement(result, target, actor))  # pyright: ignore[reportOptionalMemberAccess,reportAttributeAccessIssue]
    except discord.HTTPException as e:
        return f"公告發送失敗：{e}"
    return None


@router.post("/guilds/{guild_id}/warnings")
async def create_punishment(guild_id: int, body: PunishBody, info: SessionInfo = Depends(require_session)):
    if body.kind not in _KIND_ACTIONS:
        raise DashboardError(400, "invalid_request", fields=[_field("kind", "不是有效的種類")])
    await _KIND_PERMISSION[body.kind](guild_id, info)
    user_id, announce_id, duration, delete_seconds = _validate(body)
    kind = _KIND_NAMES[body.kind]
    reason = (body.reason or "").strip() or None

    async def _run(guild: discord.Guild) -> dict:
        target = await _resolve_user(guild, user_id, body.kind in _MEMBER_ONLY)
        actor_id = int(info.discord_user_id)
        actor = guild.get_member(actor_id) or await _resolve_user(guild, actor_id, False)
        result = await punish(
            guild,
            kind,
            target,
            actor,
            reason,
            cross_guild=body.cross_guild,
            duration=duration,
            delete_message_seconds=delete_seconds,
            via_dashboard=True,
        )
        announce_error = None
        if announce_id is not None and result.ok and not result.already:
            announce_error = await _announce(guild, announce_id, result, target, actor)
        return {"result": _result(result), "announce_error": announce_error}

    return await on_guild_async(guild_id, _run)


@router.delete("/guilds/{guild_id}/warnings/{warning_id}")
async def remove_warning(warning_id: int, guild_id: int = Depends(require_section(Section.WARNINGS, "remove"))):
    """移除本伺服器發出的紀錄；只刪資料，不解除已執行的禁言或停權。紀錄已不存在視為成功。"""

    def _remove() -> bool:
        row = sqldb.get_warning(warning_id)
        if row is None:
            return False
        if row.create_guild != guild_id:
            raise DashboardError(403, "not_this_guild")
        sqldb.remove_warning(warning_id)
        return True

    removed = await run_db(_remove)
    return {"ok": True} if removed else {"ok": True, "already": True}
