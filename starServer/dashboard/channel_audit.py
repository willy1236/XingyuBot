"""實況主後台：頻道的擋下紀錄。

GET /dashboard/channels/{twitch_id}/automod-blocks  bot 發言前被頻道 AutoMod 擋下（或檢查失敗）的最近 20 則訊息
"""

from fastapi import APIRouter, Depends

from starlib import sqldb

from .channels import ChannelAccess, require_channel
from .db import run_db

router = APIRouter(prefix="/dashboard")

#: 後台顯示的筆數
BLOCKS_LIMIT = 20


@router.get("/channels/{twitch_id}/automod-blocks")
async def list_automod_blocks(twitch_id: int, _access: ChannelAccess = Depends(require_channel)):
    def load() -> list[dict]:
        return [
            {
                "id": row.id,
                "at": row.at.isoformat(),
                "source_kind": row.source_kind,
                "source_key": row.source_key,
                "text": row.text,
                "reason": row.reason,
            }
            for row in sqldb.list_twitch_automod_blocks(twitch_id, BLOCKS_LIMIT)
        ]

    return {"blocks": await run_db(load)}
