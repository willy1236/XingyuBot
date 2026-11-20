"""實況主後台的頻道端點。

GET /dashboard/channels              這個 session 可以管理的頻道與 bot 狀態：自己的頻道在前，mod 頻道在後
GET /dashboard/channels/{twitch_id}  單一頻道的基本資料、角色、bot 狀態、轉發 Discord 的可用情形與 health（權限問題與暫停的功能）

頻道端點只用 require_channel 判斷可不可以管理某頻道，回傳 `ChannelAccess`（頻道、角色、修改紀錄的操作者）：
SessionInfo.twitch_channels 裡的頻道是 owner，不在裡面時才經 `channel_mods` 向 Twitch 確認是不是 mod。
修改設定的端點改用 require_enabled_channel，bot 還沒啟用（或已停用）時回 409 channel_not_enabled；
只有實況主能做的操作用 require_owner_channel，mod 呼叫回 403 channel_owner_only。
權限不足回 403 channel_forbidden，不用 no_permission：前端在全域把 no_permission 當成伺服器權限處理。
"""

import asyncio
from dataclasses import dataclass
from typing import Literal

from fastapi import APIRouter, Depends

from starlib import sqldb
from starlib.database import TwitchBotJoinChannel
from starlib.twitch_audit import AuditActor

from . import channel_mods
from .channel_health import channel_health, is_banned
from .db import run_db
from .errors import DashboardError
from .session import SessionInfo, TwitchIdentity, require_any_session

router = APIRouter(prefix="/dashboard")

#: 前端的頻道後台網址（後端 API 仍在 /dashboard/channels）；後端組出的導回網址都從這裡來
CHANNEL_LIST_PATH = "/dashboard/twitch"

#: 還沒有頻道列（例如析域帳號連結但從沒登入過）也視為未啟用
DEFAULT_STATE = "inactive"

#: 營運入口停權（`banned_at` 不為 null）的頻道，不論 DB 的 state 是什麼都回這個
BANNED_STATE = "banned"

type ChannelRole = Literal["owner", "mod"]


@dataclass(frozen=True, slots=True)
class ChannelAccess:
    """session 對某頻道的存取：頻道、角色，與在這個頻道修改設定時記進修改紀錄的操作者。

    實況主記成頻道本身的 Twitch 帳號（不論登入方式），mod 記成擔任該頻道 mod 的那個 Twitch 帳號。
    """

    channel: TwitchIdentity
    role: ChannelRole
    actor: AuditActor


def _owner(channel: TwitchIdentity) -> ChannelAccess:
    return ChannelAccess(channel, "owner", AuditActor("twitch", channel.id, channel.name))


def _mod(found: channel_mods.ModChannel) -> ChannelAccess:
    return ChannelAccess(found.channel, "mod", AuditActor("twitch", found.moderator.id, found.moderator.name))


def _own_ids(info: SessionInfo) -> tuple[str, ...]:
    """查 mod 頻道用的 Twitch 帳號：Twitch 登入是自己，析域登入是連結的所有 Twitch，Discord 登入沒有。"""
    return tuple(c.id for c in info.twitch_channels)


async def find_channel(info: SessionInfo, twitch_id: int) -> ChannelAccess | None:
    """這個 session 對頻道的存取；不能管理時回 None。不 raise，給整頁導覽的端點（/to/*）用。

    自己的頻道直接判為 owner，不向 Twitch 確認。
    """
    for channel in info.twitch_channels:
        if channel.id == str(twitch_id):
            return _owner(channel)
    found = await channel_mods.mod_channel(twitch_id, _own_ids(info))
    return None if found is None else _mod(found)


async def require_channel(twitch_id: int, info: SessionInfo = Depends(require_any_session)) -> ChannelAccess:
    """頻道端點的 dependency：實況主與 mod 都放行。

    Raises:
        DashboardError: 401 session_expired；403 channel_forbidden（不是自己的頻道，也確認不了是 mod）。
    """
    access = await find_channel(info, twitch_id)
    if access is None:
        raise DashboardError(403, "channel_forbidden")
    return access


async def require_enabled_channel(twitch_id: int, access: ChannelAccess = Depends(require_channel)) -> ChannelAccess:
    """修改頻道設定的端點用：同 `require_channel`，另外要求 bot 已在這個頻道啟用，沒啟用時唯讀。

    Raises:
        DashboardError: 401 session_expired；403 channel_forbidden；409 channel_not_enabled（state 不是 enabled）。
    """
    states = await run_db(lambda: _states([twitch_id]))
    if states[twitch_id] != "enabled":
        raise DashboardError(409, "channel_not_enabled")
    return access


async def require_owner_channel(access: ChannelAccess = Depends(require_channel)) -> ChannelAccess:
    """只有實況主能做的操作：同 `require_channel`，mod 回 403 channel_owner_only。

    Raises:
        DashboardError: 401 session_expired；403 channel_forbidden；403 channel_owner_only。
    """
    if access.role != "owner":
        raise DashboardError(403, "channel_owner_only")
    return access


def channel_page_path(twitch_id: int | str) -> str:
    """前端頻道頁的路徑。"""
    return f"{CHANNEL_LIST_PATH}/{twitch_id}"


def forward_access(info: SessionInfo, role: ChannelRole = "owner") -> str:
    """轉發 Discord 的可用情形：ok（析域登入且有 Discord）、need_domalyze（不是析域登入）、need_discord（析域登入但沒有 Discord）；
    mod 不論登入方式都是 mod（只看狀態）。"""
    if role == "mod":
        return "mod"
    if info.login_method != "domalyze":
        return "need_domalyze"
    return "ok" if info.discord_user_id is not None else "need_discord"


def _states(twitch_ids: list[int]) -> dict[int, str]:
    states: dict[int, str] = {}
    for twitch_id in twitch_ids:
        row = sqldb.get(TwitchBotJoinChannel, (twitch_id,))
        if row is None:
            states[twitch_id] = DEFAULT_STATE
        else:
            states[twitch_id] = BANNED_STATE if is_banned(row) else row.state
    return states


def _channel_json(channel: TwitchIdentity, role: ChannelRole, state: str) -> dict:
    return {
        "id": channel.id,
        "login": channel.login,
        "name": channel.name,
        "avatar_url": channel.avatar,
        "role": role,
        "state": state,
    }


async def channel_list(info: SessionInfo) -> list[dict]:
    """這個 session 可以管理的頻道與 bot 狀態（個人區 overview 也用它）：自己的頻道在前，mod 頻道在後，各自依名稱排序。"""
    own = sorted(info.twitch_channels, key=lambda c: (c.name.casefold(), c.id))
    mods = await channel_mods.mod_channels(_own_ids(info))
    accesses = [_owner(c) for c in own] + [_mod(m) for m in mods]
    states = await run_db(lambda: _states([int(a.channel.id) for a in accesses]))
    return [_channel_json(a.channel, a.role, states[int(a.channel.id)]) for a in accesses]


@router.get("/channels")
async def list_channels(info: SessionInfo = Depends(require_any_session)):
    return {"channels": await channel_list(info)}


@router.get("/channels/{twitch_id}")
async def get_channel(
    twitch_id: int,
    access: ChannelAccess = Depends(require_channel),
    info: SessionInfo = Depends(require_any_session),
):
    states, health = await asyncio.gather(run_db(lambda: _states([twitch_id])), channel_health(twitch_id))
    return {
        **_channel_json(access.channel, access.role, states[twitch_id]),
        "forward_access": forward_access(info, access.role),
        "health": health.to_json(),
    }
