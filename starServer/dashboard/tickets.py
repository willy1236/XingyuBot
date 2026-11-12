"""私人頻道區塊：
GET /dashboard/guilds/{id}/tickets   大廳一覽（設定、失效標示、bot 權限警告）與私人頻道清單（依大廳分組，對不到大廳的列在 unassigned）
GET /dashboard/guilds/{id}/tickets/options   編輯器用：文字頻道、分類（附 bot 權限警告）、身分組、自訂 emoji
GET /dashboard/guilds/{id}/tickets/lobbies/{channel_id}   編輯用：設定、訊息內容、衝突比對的原值
POST /dashboard/guilds/{id}/tickets/lobbies   新增大廳（既有頻道或讓 bot 新建）
PUT /dashboard/guilds/{id}/tickets/lobbies/{channel_id}   修改設定，立即更新大廳訊息；失效的大廳可重選頻道
DELETE /dashboard/guilds/{id}/tickets/lobbies/{channel_id}   移除大廳：拿掉開單按鈕，底下的私人頻道改列未歸屬
POST /dashboard/guilds/{id}/tickets/channels/{channel_id}/lock|reopen   鎖定、重開私人頻道
DELETE /dashboard/guilds/{id}/tickets/channels/{channel_id}   刪除私人頻道（對話無法復原）

權限一律經 `require_section(Section.TICKETS)`。紀錄以資料庫為準，Discord 只用來判斷失效與補名稱。
載入時，Discord 已不存在的私人頻道直接刪紀錄（不顯示，也不再占用名額）。
所有端點在伺服器 unavailable 時回 503 guild_unavailable：快取是空的，不能據此判斷頻道或訊息是否存在。
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace
from typing import Literal

import discord
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from starDiscord.ticket_channel import TicketActionError, TicketState, delete_ticket, lock_ticket, reopen_ticket
from starDiscord.ticket_lobby import LobbyConflict, LobbyError, LobbyValues, NewChannel, remove_lobby, save_lobby
from starlib import sqldb
from starlib.message_content import MessageContent, from_json
from starlib.moderation import audit_reason
from starlib.reaction_roles import emoji_valid
from starlib.tickets import (
    bot_permission_issues,
    category_permission_issues,
    default_lobby_content,
    lobby_channel_permission_issues,
    lobby_invalid_reason,
    normalize_prefix,
    prefix_error,
)

from .access import Section, ensure_guild_available, on_guild, on_guild_async, require_section
from .conflict import Conflict, check_conflict
from .db import run_db
from .errors import DashboardError
from .message_input import ensure_valid_message
from .session import SessionInfo, require_session

router = APIRouter(prefix="/dashboard")


@dataclass(frozen=True)
class _Lobby:
    """不綁 session 的大廳資料（run_db 結束後 ORM instance 會過期）"""

    channel_id: int
    message_id: int
    ticket_category_id: int | None
    name_prefix: str
    one_per_user: bool
    max_open: int | None
    manager_role_ids: list[int]


@dataclass(frozen=True)
class _Ticket:
    channel_id: int
    lobby_channel_id: int | None
    creator_id: int
    created_at: datetime
    closed_at: datetime | None
    closer_id: int | None
    number: int | None


def _load(guild_id: int) -> tuple[list[_Lobby], list[_Ticket]]:
    pairs = sqldb.list_guild_ticket_lobbies(guild_id)
    lobbies = [
        _Lobby(
            row.channel_id,
            row.message_id,
            row.ticket_category_id,
            row.name_prefix,
            row.one_per_user,
            row.max_open,
            roles,
        )
        for row, roles in pairs
    ]
    tickets = [
        _Ticket(t.channel_id, t.lobby_channel_id, t.creator_id, t.created_at, t.closed_at, t.closer_id, t.number)
        for t in sqldb.list_guild_ticket_channels(guild_id)
    ]
    return lobbies, tickets


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _member(guild: discord.Guild, user_id: int | None) -> dict | None:
    if user_id is None:
        return None
    member = guild.get_member(user_id)
    return {"id": str(user_id), "name": member.display_name if member is not None else None}


def _ticket_item(guild: discord.Guild, t: _Ticket) -> dict:
    channel = guild.get_channel(t.channel_id)
    locked = t.closed_at is not None
    return {
        "channel": {"id": str(t.channel_id), "name": channel.name if channel is not None else None},
        "jump_url": f"https://discord.com/channels/{guild.id}/{t.channel_id}",
        "creator": _member(guild, t.creator_id),
        "created_at": _iso(t.created_at),
        "number": t.number,
        "status": "locked" if locked else "open",
        "closer": _member(guild, t.closer_id) if locked else None,
        "closed_at": _iso(t.closed_at),
    }


def _sort_key(channel) -> tuple[int, int, int]:
    """已存在的頻道依「分類位置、頻道位置」，已刪除的排最後"""
    if channel is None:
        return (1, 0, 0)
    category = getattr(channel, "category", None)
    return (0, category.position if category is not None else -1, channel.position)


async def _lobby_item(guild: discord.Guild, lobby: _Lobby, tickets: list[_Ticket]) -> dict:
    channel = guild.get_channel(lobby.channel_id)
    category = guild.get_channel(lobby.ticket_category_id) if lobby.ticket_category_id is not None else None
    reason = await lobby_invalid_reason(guild, lobby)
    roles = []
    for role_id in lobby.manager_role_ids:
        role = guild.get_role(role_id)
        roles.append({"id": str(role_id), "name": role.name if role is not None else None, "invalid": role is None})
    return {
        "channel": {
            "id": str(lobby.channel_id),
            "name": channel.name if channel is not None else None,
            "invalid": reason == "channel_deleted",
        },
        "jump_url": f"https://discord.com/channels/{guild.id}/{lobby.channel_id}/{lobby.message_id}",
        "message_invalid": reason == "message_deleted",
        "category": {
            "id": str(lobby.ticket_category_id) if lobby.ticket_category_id is not None else None,
            "name": category.name if category is not None else None,
            "invalid": reason == "category_deleted",
        },
        "invalid_reason": reason,
        "manager_roles": roles,
        "name_prefix": lobby.name_prefix,
        "one_per_user": lobby.one_per_user,
        "max_open": lobby.max_open,
        # 所有還沒刪除的私人頻道都占名額，包括已鎖定的
        "ticket_count": len(tickets),
        "locked_count": sum(1 for t in tickets if t.closed_at is not None),
        "permission_issues": [
            {"permission": i.permission, "target": i.target, "consequence": i.consequence}
            for i in bot_permission_issues(guild, lobby)
        ],
        "tickets": [_ticket_item(guild, t) for t in tickets],
    }


async def _read(guild: discord.Guild, lobbies: list[_Lobby], tickets: list[_Ticket]) -> tuple[dict, list[int]]:
    # unavailable 時「頻道不在」不代表已刪除，不能據此刪紀錄，清單也會全部誤標失效，所以整個請求回 503
    ensure_guild_available(guild)
    # 只有 guild.get_channel 回 None 才視為已刪除
    gone = [t.channel_id for t in tickets if guild.get_channel(t.channel_id) is None]
    gone_set = set(gone)
    alive = [t for t in tickets if t.channel_id not in gone_set]
    lobby_ids = {lobby.channel_id for lobby in lobbies}
    by_lobby: dict[int, list[_Ticket]] = {lobby.channel_id: [] for lobby in lobbies}
    unassigned: list[_Ticket] = []
    for t in alive:
        if t.lobby_channel_id in lobby_ids:
            by_lobby[t.lobby_channel_id].append(t)
        else:
            unassigned.append(t)
    ordered = sorted(lobbies, key=lambda lobby: _sort_key(guild.get_channel(lobby.channel_id)))
    # 每個大廳要打一次 Discord 讀大廳訊息，並行處理
    items = await asyncio.gather(*(_lobby_item(guild, lobby, by_lobby[lobby.channel_id]) for lobby in ordered))
    return {"lobbies": items, "unassigned": [_ticket_item(guild, t) for t in unassigned]}, gone


@router.get("/guilds/{guild_id}/tickets")
async def list_tickets(guild_id: int = Depends(require_section(Section.TICKETS))):
    lobbies, tickets = await run_db(lambda: _load(guild_id))
    result, gone = await on_guild_async(guild_id, lambda guild: _read(guild, lobbies, tickets))
    if gone:
        await run_db(lambda: sqldb.delete_ticket_channels(gone))
    return result


# ====== 編輯 ======
MAX_BUTTON_LABEL = 80  # Discord 按鈕 label 上限
MAX_BUTTON_EMOJI = 100  # 欄位長度
MAX_OPEN_LIMIT = 10000
MAX_CHANNEL_NAME = 100  # Discord 頻道名稱上限
#: 大廳設定中參與衝突比對的資料庫欄位（管理身分組另外比對）
_ORIGINAL_COLUMNS = (
    "ticket_category_id",
    "name_prefix",
    "one_per_user",
    "max_open",
    "content_json",
    "button_label",
    "button_emoji",
)


class ExistingChannelIn(BaseModel):
    kind: Literal["existing"]
    id: int | str


class NewChannelIn(BaseModel):
    kind: Literal["new"]
    name: str
    category_id: int | str


class OriginalIn(BaseModel):
    """打開表單時看到的設定（`GET .../lobbies/{channel_id}` 的 `original`）"""

    ticket_category_id: int | str | None = None
    name_prefix: str
    one_per_user: bool
    max_open: int | None = None
    content_json: str | None = None
    button_label: str | None = None
    button_emoji: str | None = None
    manager_role_ids: list[int | str] = []


class LobbyBody(BaseModel):
    lobby_channel: ExistingChannelIn | NewChannelIn
    ticket_category_id: int | str
    manager_role_ids: list[int | str] = []
    name_prefix: str
    one_per_user: bool = True
    max_open: int | None = None
    message: MessageContent
    button_label: str | None = None
    button_emoji: str | None = None


class UpdateBody(LobbyBody):
    original: OriginalIn


class DeleteBody(BaseModel):
    original: OriginalIn


def _field(path: str, reason: str) -> dict:
    return {"path": path, "reason": reason}


def _int(value: int | str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


def _blank_to_none(value: str | None) -> str | None:
    return (value or "").strip() or None


def _actor(guild: discord.Guild, info: SessionInfo) -> discord.Member:
    member = guild.get_member(int(info.discord_user_id))
    if member is None:
        raise DashboardError(403, "no_permission")
    return member


def _roles_key(role_ids: list) -> str:
    """管理身分組的衝突比對值：排序後以逗號串接的字串"""
    return ",".join(sorted(str(r) for r in role_ids))


def _current(snap: dict) -> dict:
    return {**{k: snap[k] for k in _ORIGINAL_COLUMNS}, "manager_role_ids": _roles_key(snap["manager_role_ids"])}


def _original(o: OriginalIn) -> dict:
    return {
        "ticket_category_id": None if o.ticket_category_id is None else _int(o.ticket_category_id),
        "name_prefix": o.name_prefix,
        "one_per_user": o.one_per_user,
        "max_open": o.max_open,
        "content_json": o.content_json,
        "button_label": _blank_to_none(o.button_label),
        "button_emoji": _blank_to_none(o.button_emoji),
        "manager_role_ids": _roles_key(o.manager_role_ids),
    }


def _error(e: LobbyError) -> DashboardError:
    """`LobbyError` 轉成回應；`LobbyConflict` 由呼叫端處理（需要最新內容）"""
    match e.code:
        case "channel_not_found":
            return DashboardError(400, "invalid_request", fields=[_field("lobby_channel", "找不到這個文字頻道")])
        case "category_not_found":
            return DashboardError(
                400, "invalid_request", fields=[_field("lobby_channel.category_id", "找不到這個分類")]
            )
        case "channel_in_use":
            return DashboardError(
                400,
                "invalid_request",
                fields=[_field("lobby_channel", "目前的大廳頻道還在，不能更換；請移除這個大廳後重新新增")],
            )
        case "channel_access":
            return DashboardError(
                400,
                "bot_missing_permission",
                fields=[
                    _field(
                        "lobby_channel",
                        "我在大廳頻道缺少 View Channel 或 Read Message History 權限，讀不到大廳訊息，無法更新；請補上權限後再儲存",
                    )
                ],
            )
        case "lobby_exists":
            return DashboardError(400, "invalid_request", fields=[_field("lobby_channel", "這個頻道已經是大廳")])
        case "discord_error":
            return DashboardError(502, "discord_error", message=e.message)
        case _:
            return DashboardError(500, "save_failed")


def _parse(
    guild: discord.Guild, body: LobbyBody, old: dict | None, reason: str, prev: int | None, original: dict | None
) -> LobbyValues:
    """欄位格式與規則；不合規則丟 400 invalid_request 並附 fields。頻道是否存在由 `save_lobby` 檢查。"""
    errors: list[dict] = []

    ticket_category_id = _int(body.ticket_category_id)
    category = guild.get_channel(ticket_category_id) if ticket_category_id is not None else None
    if category is None or category.type != discord.ChannelType.category:
        errors.append(_field("ticket_category_id", "找不到這個分類"))

    error = prefix_error(body.name_prefix)
    if error is not None:
        errors.append(_field("name_prefix", error))

    if body.max_open is not None and not 1 <= body.max_open <= MAX_OPEN_LIMIT:
        errors.append(_field("max_open", f"必須是 1 到 {MAX_OPEN_LIMIT}，不限制請留空"))

    label = _blank_to_none(body.button_label)
    if label is not None and len(label) > MAX_BUTTON_LABEL:
        errors.append(_field("button_label", f"不能超過 {MAX_BUTTON_LABEL} 字"))
    emoji = _blank_to_none(body.button_emoji)
    if emoji is not None:
        if len(emoji) > MAX_BUTTON_EMOJI:
            errors.append(_field("button_emoji", "emoji 格式不正確"))
        elif (old is None or emoji != old["button_emoji"]) and not emoji_valid(guild, emoji):
            errors.append(_field("button_emoji", "這個 emoji 不屬於這個伺服器"))

    kept = set(old["manager_role_ids"]) if old is not None else set()
    role_ids: list[int] = []
    for i, raw in enumerate(body.manager_role_ids):
        role_id = _int(raw)
        path = f"manager_role_ids.{i}"
        if role_id is None:
            errors.append(_field(path, "必須是 Discord ID"))
        elif role_id in role_ids:
            errors.append(_field(path, "同一個身分組只能出現一次"))
        else:
            role_ids.append(role_id)
            role = guild.get_role(role_id)
            # 已經設定的身分組（含已被刪除的）照舊放行，才能順手移除
            if role_id not in kept and (role is None or role.is_default() or role.managed):
                errors.append(_field(path, "找不到這個身分組，或是 @everyone、整合服務管理的身分組"))

    channel: int | NewChannel
    match body.lobby_channel:
        case ExistingChannelIn(id=raw):
            parsed = _int(raw)
            if parsed is None:
                errors.append(_field("lobby_channel", "必須是 Discord ID"))
            channel = parsed or 0
        case NewChannelIn(name=name, category_id=raw_category):
            new_name = name.strip()
            parsed_category = _int(raw_category)
            if not new_name or len(new_name) > MAX_CHANNEL_NAME:
                errors.append(_field("lobby_channel.name", f"必須是 1 到 {MAX_CHANNEL_NAME} 個字元"))
            if parsed_category is None:
                errors.append(_field("lobby_channel.category_id", "必須是 Discord ID"))
            channel = NewChannel(new_name, parsed_category or 0)

    if errors:
        raise DashboardError(400, "invalid_request", fields=errors)
    assert ticket_category_id is not None
    return LobbyValues(
        channel=channel,
        ticket_category_id=ticket_category_id,
        manager_role_ids=role_ids,
        name_prefix=normalize_prefix(body.name_prefix),
        one_per_user=body.one_per_user,
        max_open=body.max_open,
        message=body.message,
        button_label=label,
        button_emoji=emoji,
        reason=reason,
        previous_channel_id=prev,
        original=original,
    )


async def _detail(guild: discord.Guild, snap: dict) -> dict:
    """編輯用內容；沒有存下內容時 `content` 是預設內容，`original.content_json` 仍是 null"""
    content = None
    if snap["content_json"] is not None:
        try:
            content = from_json(snap["content_json"])
        except ValueError:
            content = None
    if content is None:
        avatar = getattr(guild.me, "display_avatar", None)
        content = default_lobby_content(avatar.url if avatar is not None else None)
    channel = guild.get_channel(snap["channel_id"])
    ref = SimpleNamespace(
        channel_id=snap["channel_id"], message_id=snap["message_id"], ticket_category_id=snap["ticket_category_id"]
    )
    role_ids = [str(r) for r in snap["manager_role_ids"]]
    category_id = None if snap["ticket_category_id"] is None else str(snap["ticket_category_id"])
    return {
        "channel": {"id": str(snap["channel_id"]), "name": channel.name if channel is not None else None},
        "invalid_reason": await lobby_invalid_reason(guild, ref),  # pyright: ignore[reportArgumentType]
        "ticket_category_id": category_id,
        "manager_role_ids": role_ids,
        "name_prefix": snap["name_prefix"],
        "one_per_user": snap["one_per_user"],
        "max_open": snap["max_open"],
        "content": content.model_dump(),
        "button_label": snap["button_label"],
        "button_emoji": snap["button_emoji"],
        "original": {
            "ticket_category_id": category_id,
            "name_prefix": snap["name_prefix"],
            "one_per_user": snap["one_per_user"],
            "max_open": snap["max_open"],
            "content_json": snap["content_json"],
            "button_label": snap["button_label"],
            "button_emoji": snap["button_emoji"],
            "manager_role_ids": role_ids,
        },
    }


def _is_active(snap: dict | None, guild_id: int) -> bool:
    return snap is not None and snap["removed_at"] is None and snap["guild_id"] == guild_id


async def _active_snapshot(guild_id: int, channel_id: int) -> dict:
    """還在使用的大廳；不存在、已移除或不屬於這個伺服器回 409 conflict（deleted）"""
    snap = await run_db(lambda: sqldb.get_ticket_lobby_snapshot(channel_id))
    if snap is None or not _is_active(snap, guild_id):
        raise Conflict(None).to_error()
    return snap


async def _conflict(guild: discord.Guild, guild_id: int, channel_id: int) -> DashboardError:
    """衝突的回應：附最新內容，大廳已被移除則 deleted"""
    snap = await run_db(lambda: sqldb.get_ticket_lobby_snapshot(channel_id))
    if snap is None or not _is_active(snap, guild_id):
        return Conflict(None).to_error()
    return DashboardError(409, "conflict", deleted=False, current=await _detail(guild, snap))


def _result(r) -> dict:
    return {
        "channel_id": str(r.channel_id),
        "message_id": str(r.message_id),
        "jump_url": r.jump_url,
        "failures": [{"channel_id": str(f.channel_id), "reason": f.reason} for f in r.failures],
    }


def _issues(issues: list) -> list[dict]:
    return [{"permission": i.permission, "target": i.target, "consequence": i.consequence} for i in issues]


def _options_payload(guild: discord.Guild) -> dict:
    return {
        "channels": [
            {
                "id": str(c.id),
                "name": c.name,
                "category": c.category.name if c.category is not None else None,
                "permission_issues": _issues(lobby_channel_permission_issues(guild, c)),
            }
            for c in sorted(
                guild.text_channels, key=lambda c: (c.category.position if c.category else -1, c.position, c.id)
            )
        ],
        "categories": [
            {"id": str(c.id), "name": c.name, "permission_issues": _issues(category_permission_issues(guild, c))}
            for c in sorted(guild.categories, key=lambda c: (c.position, c.id))
        ],
        "roles": [
            {
                "id": str(r.id),
                "name": r.name,
                "color": r.color.value,
                "disabled_reason": "無法選擇 @everyone 或由整合服務管理的身分組"
                if r.is_default() or r.managed
                else None,
            }
            for r in sorted(guild.roles, key=lambda r: r.position, reverse=True)
        ],
        "emojis": [{"id": str(e.id), "name": e.name, "animated": e.animated, "value": str(e)} for e in guild.emojis],
    }


@router.get("/guilds/{guild_id}/tickets/options")
async def get_options(guild_id: int = Depends(require_section(Section.TICKETS))):
    def _options(guild: discord.Guild) -> dict:
        ensure_guild_available(guild)
        return _options_payload(guild)

    return await on_guild(guild_id, _options)


@router.get("/guilds/{guild_id}/tickets/lobbies/{channel_id}")
async def get_lobby(channel_id: int, guild_id: int = Depends(require_section(Section.TICKETS))):
    snap = await run_db(lambda: sqldb.get_ticket_lobby_snapshot(channel_id))
    if snap is None or not _is_active(snap, guild_id):
        raise DashboardError(404, "lobby_not_found")

    async def _get(guild: discord.Guild) -> dict:
        ensure_guild_available(guild)
        return await _detail(guild, snap)

    return await on_guild_async(guild_id, _get)


@router.post("/guilds/{guild_id}/tickets/lobbies")
async def create_lobby(
    body: LobbyBody,
    guild_id: int = Depends(require_section(Section.TICKETS)),
    info: SessionInfo = Depends(require_session),
):
    ensure_valid_message(body.message)

    async def _create(guild: discord.Guild) -> dict:
        ensure_guild_available(guild)
        actor = _actor(guild, info)
        values = _parse(guild, body, None, audit_reason(actor, "新增私人頻道大廳", True), None, None)
        try:
            return _result(await save_lobby(guild, values))
        except LobbyError as e:
            raise _error(e) from None

    return await on_guild_async(guild_id, _create)


@router.put("/guilds/{guild_id}/tickets/lobbies/{channel_id}")
async def update_lobby(
    channel_id: int,
    body: UpdateBody,
    guild_id: int = Depends(require_section(Section.TICKETS)),
    info: SessionInfo = Depends(require_session),
):
    ensure_valid_message(body.message)
    original = _original(body.original)

    async def _update(guild: discord.Guild) -> dict:
        ensure_guild_available(guild)
        actor = _actor(guild, info)
        snap = await _active_snapshot(guild_id, channel_id)
        if check_conflict(_current(snap), original) is not None:
            raise await _conflict(guild, guild_id, channel_id)
        reason = audit_reason(actor, "修改私人頻道大廳", True)
        values = _parse(guild, body, snap, reason, channel_id, {k: original[k] for k in _ORIGINAL_COLUMNS})
        try:
            return _result(await save_lobby(guild, values))
        except LobbyConflict:
            raise await _conflict(guild, guild_id, channel_id) from None
        except LobbyError as e:
            raise _error(e) from None

    return await on_guild_async(guild_id, _update)


@router.delete("/guilds/{guild_id}/tickets/lobbies/{channel_id}")
async def delete_lobby(channel_id: int, body: DeleteBody, guild_id: int = Depends(require_section(Section.TICKETS))):
    original = _original(body.original)

    async def _delete(guild: discord.Guild) -> dict:
        ensure_guild_available(guild)
        snap = await _active_snapshot(guild_id, channel_id)
        if check_conflict(_current(snap), original) is not None:
            raise await _conflict(guild, guild_id, channel_id)
        try:
            button_removed = await remove_lobby(guild, channel_id)
        except LobbyError as e:
            raise _error(e) from None
        # 按鈕沒拿掉（bot 對大廳頻道缺權限）時大廳仍已移除，成員不能再開單；由畫面說明要補權限或手動刪訊息
        return {"removed": True, "button_removed": button_removed}

    return await on_guild_async(guild_id, _delete)


# ====== 鎖定、重開與刪除私人頻道（P-04） ======
def _action_error(e: TicketActionError) -> DashboardError:
    match e.code:
        case "not_found":
            return DashboardError(404, "not_found")
        case "channel_gone":
            # 頻道已在 Discord 被刪除，紀錄已清掉；畫面重新載入清單即可
            return DashboardError(404, "not_found", message="這個私人頻道已在 Discord 被刪除")
        case "bot_missing_permission":
            return DashboardError(
                400, "bot_missing_permission", message="我缺少這個頻道的 Manage Roles 或 Manage Channels 權限"
            )
        case "discord_error":
            return DashboardError(502, "discord_error", message=e.message)
        case _:
            return DashboardError(500, "save_failed")


def _state(s: TicketState) -> dict:
    return {"channel_id": str(s.channel_id), "status": s.status, "changed": s.changed}


async def _ticket_action(guild_id: int, info: SessionInfo, run) -> dict:
    """權限已由 `require_section` 檢查（Manage Channels）；目標已是要求狀態時回 `changed: false`。"""

    async def _do(guild: discord.Guild) -> dict:
        ensure_guild_available(guild)
        actor = _actor(guild, info)
        try:
            return _state(await run(guild, actor))
        except TicketActionError as e:
            raise _action_error(e) from None

    return await on_guild_async(guild_id, _do)


@router.post("/guilds/{guild_id}/tickets/channels/{channel_id}/lock")
async def lock_channel(
    channel_id: int,
    guild_id: int = Depends(require_section(Section.TICKETS)),
    info: SessionInfo = Depends(require_session),
):
    return await _ticket_action(
        guild_id,
        info,
        lambda guild, actor: lock_ticket(guild, channel_id, actor, audit_reason(actor, "鎖定私人頻道", True)),
    )


@router.post("/guilds/{guild_id}/tickets/channels/{channel_id}/reopen")
async def reopen_channel(
    channel_id: int,
    guild_id: int = Depends(require_section(Section.TICKETS)),
    info: SessionInfo = Depends(require_session),
):
    return await _ticket_action(
        guild_id,
        info,
        lambda guild, actor: reopen_ticket(guild, channel_id, actor, audit_reason(actor, "重新開啟私人頻道", True)),
    )


@router.delete("/guilds/{guild_id}/tickets/channels/{channel_id}")
async def delete_channel(
    channel_id: int,
    guild_id: int = Depends(require_section(Section.TICKETS)),
    info: SessionInfo = Depends(require_session),
):
    return await _ticket_action(
        guild_id,
        info,
        lambda guild, actor: delete_ticket(guild, channel_id, audit_reason(actor, "刪除私人頻道", True)),
    )
