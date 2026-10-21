"""身分解析器：解析流程（假的 auth server，真實 PostgreSQL，交易結束後 rollback）與 auth server adapter。"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from aiohttp import web
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from starlib import sqldb
from starlib.identity import Account, DirectoryUnavailable, DomalyzeIdentityClient, IdentityResolver, IdentityUnavailable
from starlib.database.postgresql.client import SQLRepository
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

    async def find_by_discord(self, discord_id: int) -> Account | None:
        self.calls += 1
        if self.unavailable:
            raise DirectoryUnavailable("down")
        return self.accounts.get(discord_id)


def _account(account_id: UUID | None = None, **kwargs) -> Account:
    return Account(
        account_id=account_id or uuid4(),
        username=kwargs.get("username", "citizen"),
        roles=kwargs.get("roles", ("member",)),
        suspended=kwargs.get("suspended", False),
    )


@pytest.fixture
def directory() -> FakeDirectory:
    return FakeDirectory()


@pytest.fixture
def resolver(directory, repo) -> IdentityResolver:
    return IdentityResolver(directory, repo, TTL)


def resolve(resolver: IdentityResolver, discord_id: int = DISCORD_ID, **kwargs):
    return asyncio.run(resolver.resolve(discord_id, **kwargs))


def expire(repo: SQLRepository, discord_id: int = DISCORD_ID):
    record = repo.get_discord_identity(discord_id)
    record.checked_at = nowtz() - TTL - timedelta(seconds=1)
    repo.save_discord_identity(record)


class TestResolve:
    def test_not_found_issues_stable_temporary_id(self, resolver, repo, directory):
        first = resolve(resolver)
        expire(repo)
        second = resolve(resolver)

        assert not first.is_formal
        assert first.username is None
        assert second.user_id == first.user_id
        assert repo.get_discord_identity(DISCORD_ID).user_id == first.user_id
        assert directory.calls == 2

    def test_found_returns_formal_account(self, resolver, repo, directory):
        account = _account(username="willy", roles=("admin", "member"), suspended=True)
        directory.accounts[DISCORD_ID] = account

        identity = resolve(resolver)

        assert identity.user_id == account.account_id
        assert identity.is_formal
        assert identity.username == "willy"
        assert identity.roles == ("admin", "member")
        assert identity.suspended
        record = repo.get_discord_identity(DISCORD_ID)
        assert (record.user_id, record.is_formal, record.username, record.roles, record.suspended) == (account.account_id, True, "willy", ["admin", "member"], True)

    def test_within_ttl_skips_auth_server(self, resolver, directory):
        directory.accounts[DISCORD_ID] = _account()
        resolve(resolver)
        resolve(resolver)
        resolve(resolver)

        assert directory.calls == 1

    def test_changed_id_merges_then_updates_record(self, resolver, repo, directory, monkeypatch):
        temporary = resolve(resolver)
        merged: list[tuple[UUID, UUID]] = []
        monkeypatch.setattr(repo, "merge_user_data", lambda old, new: merged.append((old, new)))
        account = _account()
        directory.accounts[DISCORD_ID] = account
        expire(repo)

        identity = resolve(resolver)

        assert merged == [(temporary.user_id, account.account_id)]
        assert identity.user_id == account.account_id
        assert repo.get_discord_identity(DISCORD_ID).user_id == account.account_id

    def test_merge_failure_keeps_old_record(self, resolver, repo, directory, monkeypatch):
        temporary = resolve(resolver)

        def fail(old, new):
            raise SQLAlchemyError("boom")

        monkeypatch.setattr(repo, "merge_user_data", fail)
        directory.accounts[DISCORD_ID] = _account()
        expire(repo)

        with pytest.raises(SQLAlchemyError):
            resolve(resolver)

        record = repo.get_discord_identity(DISCORD_ID)
        assert record.user_id == temporary.user_id
        assert not record.is_formal

    def test_formal_then_not_found_keeps_id_and_warns(self, resolver, repo, directory, caplog):
        account = _account()
        directory.accounts[DISCORD_ID] = account
        resolve(resolver)
        del directory.accounts[DISCORD_ID]
        expire(repo)

        with caplog.at_level("WARNING", logger="starlib.identity.resolver"):
            identity = resolve(resolver)

        assert identity.user_id == account.account_id
        assert identity.is_formal
        assert any(r.message == "identity: formal account no longer found" and r.discord_id == DISCORD_ID for r in caplog.records)
        assert nowtz() - repo.get_discord_identity(DISCORD_ID).checked_at < TTL

    def test_unavailable_with_record_reuses_record(self, resolver, repo, directory):
        account = _account()
        directory.accounts[DISCORD_ID] = account
        resolve(resolver)
        expire(repo)
        directory.unavailable = True

        identity = resolve(resolver)

        assert identity.user_id == account.account_id
        assert identity.is_formal

    def test_unavailable_without_record_raises(self, resolver, repo, directory):
        directory.unavailable = True

        with pytest.raises(IdentityUnavailable):
            resolve(resolver)
        assert repo.get_discord_identity(DISCORD_ID) is None

    def test_create_false_not_found_returns_none(self, resolver, repo):
        assert resolve(resolver, create=False) is None
        assert repo.get_discord_identity(DISCORD_ID) is None

    def test_create_false_found_returns_formal(self, resolver, directory):
        account = _account()
        directory.accounts[DISCORD_ID] = account

        assert resolve(resolver, create=False).user_id == account.account_id


class TestTemporaryIdentityRace:
    def test_second_insert_keeps_first_id(self, repo):
        first = uuid4()
        repo.create_temporary_discord_identity(DISCORD_ID, first, nowtz())
        record = repo.create_temporary_discord_identity(DISCORD_ID, uuid4(), nowtz())

        assert record.user_id == first


# ─── auth server adapter ────────────────────────────────────────────────────


async def _with_server(handler, call):
    app = web.Application()
    app.router.add_get("/v1/passports/discord/{id}", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    try:
        return await call(DomalyzeIdentityClient(f"http://127.0.0.1:{port}/", "key", timeout=0.5))
    finally:
        await runner.cleanup()


def _find(handler):
    return asyncio.run(_with_server(handler, lambda client: client.find_by_discord(DISCORD_ID)))


class TestDomalyzeIdentityClient:
    def test_found(self):
        account_id = uuid4()
        seen = {}

        async def handler(request: web.Request):
            seen["auth"] = request.headers.get("Authorization")
            seen["id"] = request.match_info["id"]
            return web.json_response({"accountId": str(account_id), "username": "willy", "name": "W", "roles": ["admin"], "passports": [], "suspended": False})

        assert _find(handler) == Account(account_id=account_id, username="willy", roles=("admin",), suspended=False)
        assert seen == {"auth": "Bearer key", "id": str(DISCORD_ID)}

    def test_not_found(self):
        async def handler(request):
            return web.json_response({"detail": "account not found"}, status=404)

        assert _find(handler) is None

    @pytest.mark.parametrize("status", [401, 500, 503])
    def test_error_status_is_unavailable(self, status):
        async def handler(request):
            return web.json_response({}, status=status)

        with pytest.raises(DirectoryUnavailable):
            _find(handler)

    def test_timeout_is_unavailable(self):
        async def handler(request):
            await asyncio.sleep(2)
            return web.json_response({})

        with pytest.raises(DirectoryUnavailable):
            _find(handler)

    def test_connection_refused_is_unavailable(self):
        client = DomalyzeIdentityClient("http://127.0.0.1:9", "key", timeout=0.5)

        with pytest.raises(DirectoryUnavailable):
            asyncio.run(client.find_by_discord(DISCORD_ID))
