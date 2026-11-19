"""實況主後台的頻道端點。

GET /dashboard/channels              這個 session 可以管理的頻道與 bot 狀態
GET /dashboard/channels/{twitch_id}  單一頻道的基本資料、bot 狀態、轉發 Discord 的可用情形與 health（權限問題與暫停的功能）

頻道端點只用 require_channel 判斷可不可以管理某頻道，依據是 SessionInfo.twitch_channels，不自己查；
修改設定的端點改用 require_enabled_channel，bot 還沒啟用（或已停用）時回 409 channel_not_enabled。
權限不足回 403 channel_forbidden，不用 no_permission：前端在全域把 no_permission 當成伺服器權限處理。
"""

import asyncio

from fastapi import APIRouter, Depends

from starlib import sqldb
from starlib.database import TwitchBotJoinChannel

from .channel_health import channel_health
from .db import run_db
from .errors import DashboardError
from .session import SessionInfo, TwitchIdentity, require_any_session

router = APIRouter(prefix="/dashboard")

#: 前端的頻道後台網址（後端 API 仍在 /dashboard/channels）；後端組出的導回網址都從這裡來
CHANNEL_LIST_PATH = "/dashboard/twitch"

#: 還沒有頻道列（例如析域帳號連結但從沒登入過）也視為未啟用
DEFAULT_STATE = "inactive"


def find_channel(info: SessionInfo, twitch_id: int) -> TwitchIdentity | None:
    """這個 session 可管理的頻道；不在清單裡回 None。不 raise，給整頁導覽的端點（/to/*）用。"""
    for channel in info.twitch_channels:
        if channel.id == str(twitch_id):
            return channel
    return None


async def require_channel(twitch_id: int, info: SessionInfo = Depends(require_any_session)) -> TwitchIdentity:
    """頻道端點的 dependency：回傳 session 可管理的那個頻道。

    Raises:
        DashboardError: 401 session_expired；403 channel_forbidden（不在這個 session 可管理的頻道裡）。
    """
    channel = find_channel(info, twitch_id)
    if channel is None:
        raise DashboardError(403, "channel_forbidden")
    return channel


async def require_enabled_channel(twitch_id: int, channel: TwitchIdentity = Depends(require_channel)) -> TwitchIdentity:
    """修改頻道設定的端點用：同 `require_channel`，另外要求 bot 已在這個頻道啟用，沒啟用時唯讀。

    Raises:
        DashboardError: 401 session_expired；403 channel_forbidden；409 channel_not_enabled（state 不是 enabled）。
    """
    states = await run_db(lambda: _states([twitch_id]))
    if states[twitch_id] != "enabled":
        raise DashboardError(409, "channel_not_enabled")
    return channel


def channel_page_path(twitch_id: int | str) -> str:
    """前端頻道頁的路徑。"""
    return f"{CHANNEL_LIST_PATH}/{twitch_id}"


def forward_access(info: SessionInfo) -> str:
    """轉發 Discord 的可用情形：ok（析域登入且有 Discord）、need_domalyze（不是析域登入）、need_discord（析域登入但沒有 Discord）。"""
    if info.login_method != "domalyze":
        return "need_domalyze"
    return "ok" if info.discord_user_id is not None else "need_discord"


def _states(twitch_ids: list[int]) -> dict[int, str]:
    states: dict[int, str] = {}
    for twitch_id in twitch_ids:
        row = sqldb.get(TwitchBotJoinChannel, (twitch_id,))
        states[twitch_id] = DEFAULT_STATE if row is None else row.state
    return states


def _channel_json(channel: TwitchIdentity, state: str) -> dict:
    return {
        "id": channel.id,
        "login": channel.login,
        "name": channel.name,
        "avatar_url": channel.avatar,
        "state": state,
    }


async def channel_list(info: SessionInfo) -> list[dict]:
    """這個 session 可以管理的頻道與 bot 狀態（個人區 overview 也用它）。"""
    states = await run_db(lambda: _states([int(c.id) for c in info.twitch_channels]))
    return [_channel_json(c, states[int(c.id)]) for c in info.twitch_channels]


@router.get("/channels")
async def list_channels(info: SessionInfo = Depends(require_any_session)):
    return {"channels": await channel_list(info)}


@router.get("/channels/{twitch_id}")
async def get_channel(
    twitch_id: int,
    channel: TwitchIdentity = Depends(require_channel),
    info: SessionInfo = Depends(require_any_session),
):
    states, health = await asyncio.gather(run_db(lambda: _states([twitch_id])), channel_health(twitch_id))
    return {
        **_channel_json(channel, states[twitch_id]),
        "forward_access": forward_access(info),
        "health": health.to_json(),
    }
