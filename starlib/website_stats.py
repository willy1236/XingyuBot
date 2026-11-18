"""網站個人區的每週析域帳號連結率與連結入口點擊（T-10）。

週一 00:00 到週日 24:00，台灣時間（UTC+8），以週一的日期為 week_start。
同一個 Discord 一週只算一個帳號；連結與否在該週結束後才結算，之後的連結或解除連結不改變過去的數字。
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from starlib import sqldb
from starlib.identity import DirectoryUnavailable
from starlib.identity.resolver import get_directory
from starlib.utils import nowtz

log = logging.getLogger(__name__)

#: 各 Discord 本週是否已記錄；週一換新的集合，同一週每個 Discord 只寫一次資料庫
_recorded: tuple[date, set[int]] = (date.min, set())


def current_week_start() -> date:
    """現在（台灣時間）所在那週的週一。"""
    today = nowtz().date()
    return today - timedelta(days=today.weekday())


def needs_recording(discord_id: int) -> bool:
    """這個 Discord 本週是否還沒記錄過；呼叫端據此決定要不要把 record_activity 丟去 DB executor。"""
    return _recorded[0] != current_week_start() or discord_id not in _recorded[1]


def record_activity(discord_id: int) -> None:
    """記下這個 Discord 本週有使用網站（同步，在 DB executor 內呼叫）；同一週只寫一次資料庫，寫入失敗時下次請求再試。"""
    global _recorded
    week = current_week_start()
    if _recorded[0] != week:
        _recorded = (week, set())
    if discord_id in _recorded[1]:
        return
    sqldb.record_website_activity(week, discord_id)
    _recorded[1].add(discord_id)


def record_link_click() -> None:
    sqldb.add_website_link_click(current_week_start())


async def settle_weeks() -> int:
    """對已結束的週中 linked 為 null 的列，以 auth server 查 Discord 是否連結且未停權並寫入；回傳寫入列數。

    auth server 不可用時留 null 並停止這一輪，下次排程再補。
    """
    pending = sqldb.get_unsettled_website_activity(current_week_start())
    directory = get_directory()
    settled = 0
    for week, discord_id in pending:
        try:
            account = await directory.find_by_discord(discord_id)
        except DirectoryUnavailable:
            log.warning("website link rate: auth server unavailable, %d rows left", len(pending) - settled)
            break
        sqldb.set_website_activity_linked(week, discord_id, account is not None and not account.suspended)
        settled += 1
    return settled


@dataclass(frozen=True)
class WeekStats:
    week_start: date
    accounts: int
    linked: int
    #: linked 仍為 null 的列數；大於 0 表示該週尚未計算完成（本週尚未結束也算）
    pending: int
    clicks: int

    @property
    def rate(self) -> float | None:
        return None if self.pending or not self.accounts else self.linked / self.accounts


def weekly_report(weeks: int = 8) -> list[WeekStats]:
    """最近 weeks 週（含本週）的統計，新到舊；沒有任何紀錄的週不列。"""
    since = current_week_start() - timedelta(weeks=weeks - 1)
    return [WeekStats(*row) for row in sqldb.get_website_weekly_stats(since)]
