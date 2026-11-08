"""GET /dashboard/guilds/{id}/notifies：伺服器目前設定的頻道通知與社群推播（唯讀）。"""

from dataclasses import dataclass

import discord
from fastapi import APIRouter, Depends

from starlib import sqldb

from .access import on_guild, require_guild_access
from .db import run_db
from .notify_fields import CHANNEL_SPECS, COMMUNITY_SPECS, NotifySpec, channel_spec, community_spec
from .validity import channel_invalid_reason, role_invalid_reason

router = APIRouter(prefix="/dashboard")


@dataclass(frozen=True)
class _Row:
    spec: NotifySpec
    channel_id: int
    role_id: int | None
    message: str | None
    #: 社群推播的對象帳號：(帳號 ID, username, display_name)
    account: tuple[str, str | None, str | None] | None = None


def _load(guild_id: int) -> list[_Row]:
    """讀出一覽用的列並轉成不綁 session 的物件；不在欄位對照表的種類略過。"""
    channels, communities = sqldb.get_dashboard_notifies(guild_id)
    rows: list[_Row] = []
    for c in channels:
        if (spec := channel_spec(c.notify_type)) is not None:
            rows.append(_Row(spec, c.channel_id, c.role_id, c.message))
    for n, info in communities:
        if (spec := community_spec(n.notify_type)) is not None:
            account = (n.community_id, info.username if info else None, info.display_name if info else None)
            rows.append(_Row(spec, n.channel_id, n.role_id, n.message, account))
    return rows


def _str(value: int | None) -> str | None:
    return None if value is None else str(value)


def _item(guild: discord.Guild, row: _Row) -> dict:
    """在 bot 的事件迴圈上呼叫。只輸出該種類用得到的欄位，`values` 是該筆目前的值（T-04 的衝突比對原始值）。"""
    spec = row.spec
    channel = guild.get_channel(row.channel_id)
    item: dict = {
        "key": spec.key,
        "name": spec.name,
        "channel": {
            "id": str(row.channel_id),
            "name": channel.name if channel else None,
            "invalid": channel_invalid_reason(guild, row.channel_id, spec.scheduled),
        },
    }
    values: dict = {"channel_id": str(row.channel_id)}
    if spec.has_role:
        role = guild.get_role(row.role_id) if row.role_id is not None else None
        item["role"] = (
            None
            if row.role_id is None
            else {
                "id": str(row.role_id),
                "name": role.name if role else None,
                "invalid": role_invalid_reason(guild, row.role_id),
            }
        )
        values["role_id"] = _str(row.role_id)
    if spec.has_message:
        item["message"] = row.message
        values["message"] = row.message
    item["values"] = values
    if row.account is not None:
        # 缺 Community 的孤兒列（或 username 為空）名稱與括號都顯示帳號 ID，仍可照常修改與刪除
        account_id, username, display_name = row.account
        handle = username or account_id
        item["account"] = {"id": account_id, "display_name": display_name or handle, "username": handle}
    return item


@router.get("/guilds/{guild_id}/notifies")
async def list_notifies(guild_id: int = Depends(require_guild_access)):
    rows = await run_db(lambda: _load(guild_id))
    order = {s.key: i for i, s in enumerate((*CHANNEL_SPECS, *COMMUNITY_SPECS))}
    rows.sort(
        key=lambda r: (
            order[r.spec.key],
            (r.account[2] or r.account[1] or r.account[0]).casefold() if r.account else "",
        )
    )
    items = await on_guild(guild_id, lambda guild: [_item(guild, r) for r in rows])
    return {
        "channel_notifies": [i for i, r in zip(items, rows, strict=True) if r.spec.kind == "channel"],
        "community_notifies": [i for i, r in zip(items, rows, strict=True) if r.spec.kind == "community"],
    }
