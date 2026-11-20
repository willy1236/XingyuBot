"""實況主後台：頻道的擋下紀錄與修改紀錄，實況主與 mod 都看得到。

GET /dashboard/channels/{twitch_id}/automod-blocks  bot 發言前被頻道 AutoMod 擋下（或檢查失敗）的最近 20 則訊息
GET /dashboard/channels/{twitch_id}/audit?page=     頻道保留的整份修改紀錄（新的在前，每頁 50 筆），與營運入口相同但不回操作者的 ID
"""

from fastapi import APIRouter, Depends

from starlib import sqldb, twitch_audit

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


@router.get("/channels/{twitch_id}/audit")
async def list_audit(twitch_id: int, page: int = 1, _access: ChannelAccess = Depends(require_channel)):
    def load() -> dict:
        entries, current, has_next = twitch_audit.list_page(twitch_id, page)
        return {"entries": [e.to_json(with_actor_id=False) for e in entries], "page": current, "has_next": has_next}

    return await run_db(load)
