"""「94共用啦」雲端資料夾的共用設定，供 /drive 與網站個人區共用。

函式都是同步的（Google API 與 sqldb 皆同步），Google API 失敗時拋出原本的例外，呼叫端自行處理。
指令端直接呼叫 set_drive_share、remove_drive_share；網站端不能讓 Google 的 HTTP 佔著 DB 連線，
所以把流程拆成「DB 讀」「HTTP」「DB 寫」三段：DB 段放進 run_db，HTTP 段放在 executor 外（asyncio.to_thread）。
"""

import logging
import re
from dataclasses import dataclass
from uuid import UUID

from starlib.database import DriveShare
from starlib.providers import XingyuGoogleCloud

from . import sqldb

log = logging.getLogger(__name__)

DRIVE_FOLDER_ID = "1bDtsLbOi5crIOkWUZbQmPq3dXUbwWEan"

_GMAIL = re.compile(r"^[^@\s]+(@gmail\.com)?$", re.IGNORECASE)


def normalize_gmail(raw: str) -> str | None:
    """`abc` 與 `abc@gmail.com`（不分大小寫）都回 `abc@gmail.com`；其他格式回 None。"""
    value = raw.strip()
    if not _GMAIL.match(value):
        return None
    return value if "@" in value else f"{value}@gmail.com"


@dataclass(frozen=True)
class SharePlan:
    """DB 讀取結果：已建立的 Google client（憑證來自 DB）與目前的共用設定。"""

    google: XingyuGoogleCloud
    #: 目前共用的信箱與權限 ID（取純值，讓 plan 能跨 thread 使用），沒有設定時為 None
    old_gmail: str | None
    old_share_id: str | None


def plan_share(user_id: UUID) -> SharePlan:
    """DB 段：讀目前的共用設定與 Google 憑證。"""
    google = XingyuGoogleCloud()
    old = sqldb.get_drive_share(user_id)
    return SharePlan(google, old.gmail if old else None, old.share_id if old else None)


def request_share(plan: SharePlan, gmail: str) -> str | None:
    """HTTP 段：共用給 gmail，已有共用時先新增新的、成功後才移除舊的；回傳新權限的 ID。

    任何一步失敗都不會改動原本的設定：舊的移除失敗時，會把剛新增的權限收回再拋出例外。
    與目前設定同一個信箱（不分大小寫）時什麼都不做，回 None。
    """
    if plan.old_gmail is not None and plan.old_gmail.lower() == gmail.lower():
        return None
    new_id = plan.google.add_file_permissions(DRIVE_FOLDER_ID, gmail)["id"]
    if plan.old_share_id is not None:
        try:
            plan.google.remove_file_permissions(DRIVE_FOLDER_ID, plan.old_share_id)
        except Exception:
            try:
                plan.google.remove_file_permissions(DRIVE_FOLDER_ID, new_id)
            except Exception:
                log.exception("Rollback of new drive permission failed", extra={"gmail": gmail})
            raise
    return new_id


def save_share(user_id: UUID, gmail: str, share_id: str | None) -> DriveShare:
    """DB 段：Google 全部成功後才寫入；share_id 為 None（沒有變動）時回傳現有設定。"""
    if share_id is None:
        return sqldb.get_drive_share(user_id)  # pyright: ignore[reportReturnType]
    return sqldb.merge(DriveShare(user_id=user_id, gmail=gmail, share_id=share_id))


def set_drive_share(user_id: UUID, gmail: str) -> DriveShare:
    """共用給 gmail；已有共用時更換。"""
    return save_share(user_id, gmail, request_share(plan_share(user_id), gmail))


def request_remove(plan: SharePlan) -> None:
    """HTTP 段：收回目前的共用權限；沒有設定時什麼都不做。"""
    if plan.old_share_id is not None:
        plan.google.remove_file_permissions(DRIVE_FOLDER_ID, plan.old_share_id)


def remove_drive_share(user_id: UUID) -> bool:
    """取消共用；原本沒有設定回 False。"""
    plan = plan_share(user_id)
    if plan.old_share_id is None:
        return False
    request_remove(plan)
    sqldb.remove_drive_share(user_id)
    return True
