"""身分系統測試共用：綁在外層交易上、測完 rollback 的 `repo` fixture，與假 auth server（FakeDirectory）。"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlmodel import Session

from starlib import sqldb
from starlib.database.postgresql.client import SQLRepository
from starlib.identity import (
    Account,
    DirectoryUnavailable,
    ResolvedAccount,
)
from starlib.utils import nowtz

TTL = timedelta(hours=1)
DISCORD_ID = 900000000000000001


@pytest.fixture
def repo():
    """綁在外層交易上的 repository，repository 內的 commit 只會提交 savepoint，測試結束整個 rollback。"""
    connection = sqldb.engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    repository = SQLRepository(sqldb.engine, session)
    try:
        yield repository
    finally:
        session.close()
        transaction.rollback()
        connection.close()


class FakeDirectory:
    def __init__(self):
        self.accounts: dict[int, Account] = {}
        self.unavailable = False
        self.calls = 0
        # find_by_account_id 的回答：沒設定的 ID 視為查無此人
        self.by_account_id: dict[UUID, ResolvedAccount] = {}
        self.account_unavailable = False
        self.account_calls = 0

    async def find_by_passport(self, provider: str, subject: str) -> Account | None:
        assert provider == "discord", "resolver 只用 Discord 查"
        return await self.find_by_discord(int(subject))

    async def find_by_discord(self, discord_id: int) -> Account | None:
        self.calls += 1
        if self.unavailable:
            raise DirectoryUnavailable("down")
        return self.accounts.get(discord_id)

    async def find_by_account_id(self, account_id: UUID) -> ResolvedAccount | None:
        self.account_calls += 1
        if self.account_unavailable or self.unavailable:
            raise DirectoryUnavailable("down")
        return self.by_account_id.get(account_id)

    async def find_by_username(self, username: str) -> Account | None:
        if self.unavailable:
            raise DirectoryUnavailable("down")
        return next((a for a in self.accounts.values() if a.username == username), None)


def _account(account_id: UUID | None = None, **kwargs) -> Account:
    return Account(
        account_id=account_id or uuid4(),
        username=kwargs.get("username", "citizen"),
        roles=kwargs.get("roles", ("member",)),
        suspended=kwargs.get("suspended", False),
        twitch_passports=tuple(kwargs.get("twitch_passports", ())),
        minecraft_passports=tuple(kwargs.get("minecraft_passports", ())),
    )


def expire(repo: SQLRepository, discord_id: int = DISCORD_ID):
    record = repo.get_discord_identity(discord_id)
    record.checked_at = nowtz() - TTL - timedelta(seconds=1)
    repo.save_discord_identity(record)
