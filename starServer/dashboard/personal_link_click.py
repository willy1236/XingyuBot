"""個人區「連結析域帳號」入口的點擊紀錄（T-10）。

POST /dashboard/personal/link-click  該週點擊次數加一；只需要 session，不需要析域帳號。
"""

from fastapi import APIRouter, Depends

from starlib import website_stats

from .db import run_db
from .session import DiscordSessionInfo, require_session

router = APIRouter(prefix="/dashboard")


@router.post("/personal/link-click", status_code=204)
async def link_click(_: DiscordSessionInfo = Depends(require_session)) -> None:
    await run_db(website_stats.record_link_click)
