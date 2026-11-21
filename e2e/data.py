"""E2E 的固定資料：一位 dashboard 使用者的 session，與個人區語音時數要排名用的紀錄。"""

from __future__ import annotations

from datetime import timedelta

from e2e.fakes import FRIEND, GUILD_ID, STRANGER, USER
from starlib.database import VoiceTime
from tests.helpers.dashboard_setup import make_session

SESSION_ID = "e2e-session"
#: (Discord ID, 分鐘)：USER 第 2 名，STRANGER 已不在伺服器內但仍在排行上
VOICE_MINUTES = {FRIEND: 300, USER: 125, STRANGER: 60}


def seed(sqldb) -> str:
    make_session(sqldb, session_id=SESSION_ID)
    for discord_id, minutes in VOICE_MINUTES.items():
        sqldb.merge(VoiceTime(discord_id=discord_id, guild_id=GUILD_ID, total_minute=timedelta(minutes=minutes)))
    return SESSION_ID
