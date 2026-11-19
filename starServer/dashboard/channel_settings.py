"""實況主後台：頻道的設定頁操作。

POST /dashboard/channels/{twitch_id}/delete-data  刪除頻道在星羽的所有資料並停用 bot（修改紀錄與停權狀態保留）
"""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import col, delete

from starlib import sqldb, twitch_tokens
from starlib.database import APIType, OAuthToken, TwitchBotJoinChannel

from . import twitch_control
from .channel_activation import _sync_bot
from .channels import DEFAULT_STATE, require_channel
from .db import run_db
from .errors import DashboardError
from .session import TwitchIdentity

log = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard")


class DeleteDataBody(BaseModel):
    confirm_login: str


def _delete_data(twitch_id: int) -> None:
    """同一個交易內清掉頻道的功能資料、實況主 token 與頻道列上的設定，最後才 commit；任何一步失敗都整筆 rollback。

    頻道列本身保留（營運入口與停權需要它），只清 action_channel_id、action_guild_id、point_name 並把 state 設回 inactive，
    banned_at 等其他欄位不碰。修改紀錄（twitch_channel_audit）不刪。
    """
    try:
        sqldb.delete_twitch_channel_data(twitch_id)
        credential_id = sqldb.get_oauth_client(APIType.Twitch, twitch_tokens.BROADCASTER_CLIENT_SEQ).credential_id
        sqldb.session.exec(
            delete(OAuthToken).where(
                col(OAuthToken.user_id) == str(twitch_id), col(OAuthToken.client_credential_id) == credential_id
            )
        )
        row = sqldb.get(TwitchBotJoinChannel, (twitch_id,))
        if row is not None:
            row.action_channel_id = None
            row.action_guild_id = None
            row.point_name = None
            row.state = DEFAULT_STATE
            sqldb.session.add(row)
        sqldb.commit()
    except Exception:
        sqldb.session.rollback()
        raise


@router.post("/channels/{twitch_id}/delete-data")
async def delete_channel_data(twitch_id: int, body: DeleteDataBody, channel: TwitchIdentity = Depends(require_channel)):
    """`confirm_login` 要等於頻道 login（大小寫不敏感），不符回 400 confirm_mismatch。不要求頻道已啟用。"""
    if body.confirm_login.strip().casefold() != channel.login.casefold():
        raise DashboardError(400, "confirm_mismatch")
    await run_db(lambda: _delete_data(twitch_id))
    log.info("Dashboard Twitch delete data: %s (%s)", channel.login, twitch_id)
    # 交易提交後 state 已是 inactive：bot 離開聊天室並退訂；離線時下次啟動依資料庫為準
    bot_offline = await _sync_bot(twitch_id)
    twitch_control.invalidate("twitch_channel", twitch_id)
    twitch_control.invalidate("twitch_cmd", twitch_id)
    twitch_control.invalidate("twitch_timer", twitch_id)
    twitch_control.invalidate("twitch_event_response", twitch_id)
    return {"state": DEFAULT_STATE, "bot_offline": bot_offline}
