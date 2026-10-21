"""由 Discord ID 取得使用者 ID：auth server 查得到用正式 account_id，明確查無此人才發臨時 ID。"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Literal, overload
from uuid import UUID, uuid4

from starlib.database.postgresql.models import DiscordIdentity
from starlib.utils import nowtz

from .client import AccountDirectory, DirectoryUnavailable, DomalyzeIdentityClient

if TYPE_CHECKING:
    from starlib.database.postgresql.client import UserRepository

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class BotIdentity:
    user_id: UUID
    is_formal: bool
    username: str | None
    roles: tuple[str, ...]
    suspended: bool


class IdentityUnavailable(Exception):
    """auth server 沒給出明確答案，且 bot 沒有這個 Discord ID 的紀錄"""


def _to_identity(record: DiscordIdentity) -> BotIdentity:
    return BotIdentity(
        user_id=record.user_id,
        is_formal=record.is_formal,
        username=record.username,
        roles=tuple(record.roles or ()),
        suspended=record.suspended,
    )


class IdentityResolver:
    def __init__(
        self,
        directory: AccountDirectory,
        repo: "UserRepository",
        ttl: timedelta,
        backoff: timedelta = timedelta(minutes=1),
        merge_backoff: timedelta = timedelta(minutes=10),
    ):
        self._directory = directory
        self._repo = repo
        self._ttl = ttl
        # auth server 沒給答案後的一段時間內，有紀錄的人直接沿用，不必每次都等逾時
        self._backoff = backoff
        self._unavailable_until: datetime | None = None
        # 搬資料失敗的人，這段時間內直接沿用舊紀錄，不重打 auth server、不重跑搬資料；只影響該使用者，重啟後清空
        self._merge_backoff = merge_backoff
        self._merge_retry_after: dict[int, datetime] = {}

    async def resolve(self, discord_id: int, *, create: bool = True) -> BotIdentity | None:
        record = self._repo.get_discord_identity(discord_id)
        if record and nowtz() - record.checked_at < self._ttl:
            return _to_identity(record)

        if record and self._unavailable_until and nowtz() < self._unavailable_until:
            return _to_identity(record)

        retry_after = self._merge_retry_after.get(discord_id)
        if retry_after:
            if record and nowtz() < retry_after:
                return _to_identity(record)
            del self._merge_retry_after[discord_id]

        try:
            account = await self._directory.find_by_discord(discord_id)
        except DirectoryUnavailable as e:
            self._unavailable_until = nowtz() + self._backoff
            # 沒有明確答案時絕不發臨時 ID，否則已有正式帳號的人會被拆成兩份資料
            if record:
                return _to_identity(record)
            raise IdentityUnavailable from e

        self._unavailable_until = None
        now = nowtz()
        if account is None:
            if record is None:
                if not create:
                    return None
                return _to_identity(self._repo.create_temporary_discord_identity(discord_id, uuid4(), now))
            if record.is_formal:
                # 域民被刪除或通行證被移除：資料留在原 ID，交給管理員處理
                log.warning("identity: formal account no longer found", extra={"discord_id": discord_id, "user_id": str(record.user_id)})
            record.checked_at = now
            return _to_identity(self._repo.save_discord_identity(record))

        merge_from = None
        if record and record.user_id != account.account_id:
            if not record.is_formal:
                merge_from = record.user_id
            else:
                try:
                    merge_from = await self._merge_source_for_formal(discord_id, record.user_id, account.account_id)
                except DirectoryUnavailable:
                    # 判斷不了就不動紀錄，下次再判斷；也不要讓每次互動都等一次逾時
                    self._unavailable_until = nowtz() + self._backoff
                    return _to_identity(record)
        previous = _to_identity(record) if record else None  # 有 merge_from 就一定有 record
        try:
            saved = self._repo.save_discord_identity(
                DiscordIdentity(
                    discord_id=discord_id,
                    user_id=account.account_id,
                    is_formal=True,
                    username=account.username,
                    roles=list(account.roles),
                    suspended=account.suspended,
                    checked_at=now,
                ),
                merge_from=merge_from,
            )
        except Exception as e:
            if merge_from is None:
                raise
            # 搬資料失敗時已整筆 rollback，紀錄與資料都還是舊 ID：這次照舊 ID 做完，下次使用再試，不讓指令跟著失敗
            log.exception(
                "identity: saving identity with merge failed, keeping the previous ID",
                extra={"discord_id": discord_id, "old_id": str(merge_from), "new_id": str(account.account_id), "error_type": type(e).__name__},
            )
            self._merge_retry_after[discord_id] = nowtz() + self._merge_backoff
            return previous
        self._merge_retry_after.pop(discord_id, None)
        return _to_identity(saved)

    async def _merge_source_for_formal(self, discord_id: int, old_id: UUID, new_id: UUID) -> UUID | None:
        """原本是正式 ID、現在指到別的域民：舊 ID 已併入新域民才搬資料，否則只改紀錄。沒得到答案時 raise DirectoryUnavailable。"""
        resolved = await self._directory.find_by_account_id(old_id)
        extra = {"discord_id": discord_id, "old_id": str(old_id), "new_id": str(new_id)}
        if resolved is None:
            log.warning("identity: previous account no longer exists, repointing without moving data", extra=extra)
            return None
        if resolved.merged_from is None:
            # 舊域民仍存在，這個 Discord 帳號只是改連到另一位域民，兩邊的資料都不動
            log.info("identity: discord account repointed to another account", extra=extra)
            return None
        if resolved.account.account_id != new_id:
            # 舊 ID 併入的是另一位域民，資料不屬於現在這位
            log.warning("identity: previous account merged into a different account, repointing without moving data", extra={**extra, "merged_into": str(resolved.account.account_id)})
            return None
        return old_id


_default: IdentityResolver | None = None


def _get_default() -> IdentityResolver:
    global _default
    if _default is None:
        from starlib.database import sqldb
        from starlib.settings import get_settings

        settings = get_settings()
        directory = DomalyzeIdentityClient(settings.AUTH_INTERNAL_URL, settings.AUTH_SERVICE_KEY, twitch_provider=settings.AUTH_TWITCH_PROVIDER)
        _default = IdentityResolver(directory, sqldb, timedelta(seconds=settings.IDENTITY_TTL_SECONDS))
    return _default


@overload
async def resolve_identity(discord_id: int, *, create: Literal[True] = True) -> BotIdentity: ...
@overload
async def resolve_identity(discord_id: int, *, create: bool) -> BotIdentity | None: ...
async def resolve_identity(discord_id: int, *, create: bool = True) -> BotIdentity | None:
    """
    取得 Discord 帳號對應的使用者 ID。

    create=True 時不會回 None；create=False 時 auth server 查無此人且沒有紀錄回 None，不發臨時 ID。
    auth server 沒給出明確答案且沒有紀錄時 raise IdentityUnavailable。
    """
    return await _get_default().resolve(discord_id, create=create)
