"""
### 模組：警告累計自動禁言
設定的預設與範圍、警告寫入後的判斷與執行。後台與 `/server setting` 共用同一套驗證。
判斷與執行都讀 Discord 物件，須在 bot 事件迴圈上呼叫。
"""

import logging
import re
from dataclasses import dataclass
from datetime import timedelta

import discord

from starlib.database import WarningType
from starlib.database.postgresql.models import (
    AUTO_TIMEOUT_DEFAULT_SECONDS,
    AUTO_TIMEOUT_DEFAULT_TIMES,
    AUTO_TIMEOUT_SECONDS_RANGE,
    AUTO_TIMEOUT_TIMES_RANGE,
    GuildSetting,
)
from starlib.dynamic_voice import LobbyPermIssue
from starlib.moderation import AutoTimeoutResult, punish, register_after_warning
from starlib.pubsub import sclient
from starlib.utils import time_to_datetime

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AutoTimeoutSetting:
    """自動禁言的有效設定：資料庫欄位為 NULL 的項目已換成預設值。"""

    enabled: bool
    times: int
    seconds: int


def effective_setting(row: GuildSetting | None) -> AutoTimeoutSetting:
    """沒有設定列（None）或欄位為 NULL 時取預設：不啟用、3 次、10 分鐘。"""
    if row is None:
        return AutoTimeoutSetting(False, AUTO_TIMEOUT_DEFAULT_TIMES, AUTO_TIMEOUT_DEFAULT_SECONDS)
    return AutoTimeoutSetting(
        bool(row.auto_timeout_enabled),
        row.timeout_after_warning_times if row.timeout_after_warning_times is not None else AUTO_TIMEOUT_DEFAULT_TIMES,
        row.auto_timeout_seconds if row.auto_timeout_seconds is not None else AUTO_TIMEOUT_DEFAULT_SECONDS,
    )


def valid_times(times: int) -> bool:
    return AUTO_TIMEOUT_TIMES_RANGE[0] <= times <= AUTO_TIMEOUT_TIMES_RANGE[1]


def valid_seconds(seconds: int) -> bool:
    return AUTO_TIMEOUT_SECONDS_RANGE[0] <= seconds <= AUTO_TIMEOUT_SECONDS_RANGE[1]


_DURATION = re.compile(r"(\d+[dhms])+")


def parse_duration(text: str) -> int | None:
    """解析 `/timeout` 同格式的時長（如 30s、1h20m、7d）成秒數；格式錯誤或超出自動禁言範圍回 None。"""
    text = text.strip().lower()
    if not _DURATION.fullmatch(text):
        return None
    seconds = int(time_to_datetime(text).total_seconds())
    return seconds if valid_seconds(seconds) else None


def format_seconds(seconds: int) -> str:
    """秒數轉成中文時長，例如 600 → 10 分鐘、5400 → 1 小時 30 分鐘。"""
    parts = []
    for unit, size in (("天", 86400), ("小時", 3600), ("分鐘", 60), ("秒", 1)):
        count, seconds = divmod(seconds, size)
        if count:
            parts.append(f"{count} {unit}")
    return " ".join(parts) or "0 秒"


def moderate_members_issue(guild: discord.Guild) -> LobbyPermIssue | None:
    """bot 缺少 Moderate Members 時回傳說明，否則 None。"""
    if guild.me.guild_permissions.moderate_members:
        return None
    return LobbyPermIssue("Moderate Members", "guild", "無法自動禁言，警告累計到次數時只會寫入警告")


async def after_warning(guild: discord.Guild, target: discord.User | discord.Member, warning_id: int) -> AutoTimeoutResult | None:
    """警告寫入後判斷是否觸發自動禁言；沒有觸發回 None。

    對象不在伺服器不算觸發。計數照目前剩下的紀錄算（`get_warning_count`：本伺服器最後一次禁言之後的警告，含剛寫入的這筆）。
    """
    setting = effective_setting(sclient.sqldb.get_guild_setting_fresh(guild.id))
    if not setting.enabled:
        return None
    member = target if isinstance(target, discord.Member) else guild.get_member(target.id)
    if member is None:
        return None
    if sclient.sqldb.get_warning_count(target.id, guild.id) < setting.times:
        return None

    duration = timedelta(seconds=setting.seconds)
    result = await punish(
        guild,
        WarningType.Timeout,
        member,
        guild.me,
        f"累計 {setting.times} 次警告自動禁言",
        cross_guild=False,
        duration=duration,
        via_dashboard=False,
    )
    if not result.ok:
        log.info("auto timeout failed", extra={"guild_id": guild.id, "user_id": target.id, "error": result.error})
        return AutoTimeoutResult(ok=False, error=result.error)
    # 禁言已執行但紀錄沒寫入時，error 帶著原因，計數不會歸零
    return AutoTimeoutResult(ok=True, duration=duration, error=result.error)


def register() -> None:
    """把自動禁言掛到懲處服務的警告後鉤子；重複呼叫無妨。"""
    register_after_warning(after_warning)
