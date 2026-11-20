"""bot owner 營運入口的網站部分：每週析域帳號連結率與連結入口點擊。

GET /dashboard/ops/website?weeks=  最近 weeks 週（含本週，1–52）的統計，新到舊；沒有任何紀錄的週不列

權限同 `ops.py`：只放行 bot owner，不是回 403 not_bot_owner。
"""

from fastapi import APIRouter, Depends

from starlib import website_stats

from .db import run_db
from .ops import require_bot_owner
from .session import SessionInfo

router = APIRouter(prefix="/dashboard/ops/website")

WEEKS_DEFAULT = 8
WEEKS_MAX = 52


@router.get("")
async def weekly(weeks: int = WEEKS_DEFAULT, _: SessionInfo = Depends(require_bot_owner)):
    stats = await run_db(lambda: website_stats.weekly_report(min(max(weeks, 1), WEEKS_MAX)))
    return {
        "weeks": [
            {
                "week_start": s.week_start.isoformat(),
                "accounts": s.accounts,
                "linked": s.linked,
                "pending": s.pending,
                "clicks": s.clicks,
                "rate": s.rate,
            }
            for s in stats
        ]
    }
