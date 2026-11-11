"""私人頻道區塊：
GET /dashboard/guilds/{id}/tickets   大廳一覽（設定、失效標示、bot 權限警告）與私人頻道清單（依大廳分組，對不到大廳的列在 unassigned）

權限一律經 `require_section(Section.TICKETS)`。紀錄以資料庫為準，Discord 只用來判斷失效與補名稱。
載入時，Discord 已不存在的私人頻道直接刪紀錄（不顯示，也不再占用名額）。
"""

from dataclasses import dataclass
from datetime import datetime

import discord
from fastapi import APIRouter, Depends

from starlib import sqldb
from starlib.tickets import bot_permission_issues, lobby_invalid_reason

from .access import Section, on_guild_async, require_section
from .db import run_db

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
    # 只有 guild.get_channel 回 None 才視為已刪除；bot 已 ready 且在該伺服器（require_section 保證）
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
    items = [await _lobby_item(guild, lobby, by_lobby[lobby.channel_id]) for lobby in ordered]
    return {"lobbies": items, "unassigned": [_ticket_item(guild, t) for t in unassigned]}, gone


@router.get("/guilds/{guild_id}/tickets")
async def list_tickets(guild_id: int = Depends(require_section(Section.TICKETS))):
    lobbies, tickets = await run_db(lambda: _load(guild_id))
    result, gone = await on_guild_async(guild_id, lambda guild: _read(guild, lobbies, tickets))
    if gone:
        await run_db(lambda: sqldb.delete_ticket_channels(gone))
    return result
