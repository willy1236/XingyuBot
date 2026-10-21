"""由 Discord ID 取得使用者 ID：auth server 查得到用正式 account_id，明確查無此人才發臨時 ID。"""

import logging
from dataclasses import dataclass
from datetime import timedelta
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
    def __init__(self, directory: AccountDirectory, repo: "UserRepository", ttl: timedelta):
        self._directory = directory
        self._repo = repo
        self._ttl = ttl

    async def resolve(self, discord_id: int, *, create: bool = True) -> BotIdentity | None:
        record = self._repo.get_discord_identity(discord_id)
        if record and nowtz() - record.checked_at < self._ttl:
            return _to_identity(record)

        try:
            account = await self._directory.find_by_discord(discord_id)
        except DirectoryUnavailable as e:
            # 沒有明確答案時絕不發臨時 ID，否則已有正式帳號的人會被拆成兩份資料
            if record:
                return _to_identity(record)
            raise IdentityUnavailable from e

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

        merge_from = record.user_id if record and record.user_id != account.account_id else None
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
        return _to_identity(saved)


_default: IdentityResolver | None = None


def _get_default() -> IdentityResolver:
    global _default
    if _default is None:
        from starlib.database import sqldb
        from starlib.settings import get_settings

        settings = get_settings()
        directory = DomalyzeIdentityClient(settings.AUTH_INTERNAL_URL, settings.AUTH_SERVICE_KEY)
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
