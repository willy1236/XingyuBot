"""頻道設定的修改紀錄。web 端的後台端點與 Twitch bot 的聊天室指令都經這裡寫入與查詢。

寫入跟呼叫端的 DB session 同一個交易：`record_change` 只加進 session，不 commit，
業務資料與紀錄一起提交或一起 rollback，不會有「改了沒紀錄」或「有紀錄沒改」。
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from sqlmodel import col, select

from starlib.database import TwitchChannelAudit, sqldb

type AuditSource = Literal["dashboard", "chat"]
type AuditTarget = Literal["command", "timer", "event_response", "forward", "channel", "mod_collab"]
type AuditAction = Literal["create", "update", "delete"]


@dataclass(frozen=True, slots=True)
class AuditActor:
    """操作者：Twitch、Discord 或析域帳號（沒有 Discord 身分的析域登入，id 是 account_id）。"""

    platform: Literal["twitch", "discord", "domalyze"]
    id: str
    name: str


@dataclass(frozen=True, slots=True)
class AuditEntry:
    id: int
    at: datetime
    actor: AuditActor
    source: AuditSource
    target_kind: AuditTarget
    target_key: str
    action: AuditAction
    before: dict[str, Any] | None
    after: dict[str, Any] | None

    def to_json(self, *, with_actor_id: bool = True) -> dict[str, Any]:
        """後台回應用的形狀；頻道後台不回操作者的 ID（with_actor_id=False），營運入口回。"""
        actor: dict[str, Any] = {"platform": self.actor.platform, "name": self.actor.name}
        if with_actor_id:
            actor["id"] = self.actor.id
        return {
            "id": self.id,
            "at": self.at.isoformat(),
            "actor": actor,
            "source": self.source,
            "target_kind": self.target_kind,
            "target_key": self.target_key,
            "action": self.action,
            "before": self.before,
            "after": self.after,
        }


#: 後台修改紀錄每頁的筆數
PAGE_SIZE = 50


def record_change(
    twitch_id: int,
    actor: AuditActor,
    source: AuditSource,
    target_kind: AuditTarget,
    target_key: str,
    action: AuditAction,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    """記一筆修改，在呼叫端的 DB session 內寫入、不 commit。

    before、after 是可序列化的欄位快照；新增時 before 為 None，刪除時 after 為 None。
    """
    sqldb.session.add(
        TwitchChannelAudit(
            twitch_id=twitch_id,
            actor_platform=actor.platform,
            actor_id=actor.id,
            actor_name=actor.name,
            source=source,
            target_kind=target_kind,
            target_key=target_key,
            action=action,
            before=before,
            after=after,
        )
    )


def list_changes(twitch_id: int, offset: int = 0, limit: int = 50) -> list[AuditEntry]:
    """頻道的修改紀錄，新的在前。同步函式，要在 DB worker thread 上呼叫。"""
    stmt = (
        select(TwitchChannelAudit)
        .where(TwitchChannelAudit.twitch_id == twitch_id)
        .order_by(col(TwitchChannelAudit.at).desc(), col(TwitchChannelAudit.id).desc())
        .offset(offset)
        .limit(limit)
    )
    return [
        AuditEntry(
            id=row.id,  # pyright: ignore[reportArgumentType]
            at=row.at,
            actor=AuditActor(row.actor_platform, row.actor_id, row.actor_name),  # pyright: ignore[reportArgumentType]
            source=row.source,  # pyright: ignore[reportArgumentType]
            target_kind=row.target_kind,  # pyright: ignore[reportArgumentType]
            target_key=row.target_key,
            action=row.action,  # pyright: ignore[reportArgumentType]
            before=row.before,
            after=row.after,
        )
        for row in sqldb.session.exec(stmt).all()
    ]


def list_page(twitch_id: int, page: int) -> tuple[list[AuditEntry], int, bool]:
    """後台分頁用：第 page 頁（小於 1 視為 1）的紀錄、實際的頁碼與有沒有下一頁。同步函式，要在 DB worker thread 上呼叫。"""
    page = max(page, 1)
    # 多讀一筆判斷有沒有下一頁
    entries = list_changes(twitch_id, (page - 1) * PAGE_SIZE, PAGE_SIZE + 1)
    return entries[:PAGE_SIZE], page, len(entries) > PAGE_SIZE
