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
from starlib.identity import Account, DirectoryUnavailable, DomalyzeIdentityClient, IdentityResolver, IdentityUnavailable, LinkedPassport, ResolvedAccount
from starlib.database import LinkedAccount, PlatformType
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
        # find_by_account_id 的回答：沒設定的 ID 視為查無此人
        self.by_account_id: dict[UUID, ResolvedAccount] = {}
        self.account_unavailable = False
        self.account_calls = 0

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

    def test_merge_failure_keeps_old_record(self, resolver, repo, directory, monkeypatch, caplog):
        temporary = resolve(resolver)

        def fail(old, new):
            raise SQLAlchemyError("boom")

        monkeypatch.setattr(repo, "merge_user_data", fail)
        directory.accounts[DISCORD_ID] = _account()
        expire(repo)

        with caplog.at_level("ERROR", logger="starlib.identity.resolver"):
            identity = resolve(resolver)

        # 這次照舊 ID 做完，不讓指令跟著失敗
        assert identity == temporary
        assert any(r.levelname == "ERROR" and r.discord_id == DISCORD_ID for r in caplog.records)
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

    def test_unavailable_backs_off_for_known_users(self, resolver, repo, directory):
        directory.accounts[DISCORD_ID] = _account()
        resolve(resolver)
        expire(repo)
        directory.unavailable = True
        resolve(resolver)
        resolve(resolver)

        assert directory.calls == 2

    def test_backoff_still_asks_for_unknown_users(self, resolver, directory):
        directory.unavailable = True
        for _ in range(2):
            with pytest.raises(IdentityUnavailable):
                resolve(resolver)

        assert directory.calls == 2

    def test_create_false_not_found_returns_none(self, resolver, repo):
        assert resolve(resolver, create=False) is None
        assert repo.get_discord_identity(DISCORD_ID) is None

    def test_create_false_found_returns_formal(self, resolver, directory):
        account = _account()
        directory.accounts[DISCORD_ID] = account

        assert resolve(resolver, create=False).user_id == account.account_id


D2 = DISCORD_ID + 1


def _names(repo: SQLRepository, user_id: UUID) -> list[str]:
    return sorted(p.name for p in repo.get_music_playlists(user_id))


class TestIdentityChange:
    """ID 改變時判斷要不要搬資料：假的 auth server，真實 PostgreSQL 上的 merge_user_data"""

    def _formal(self, resolver, directory, discord_id=DISCORD_ID, account=None):
        account = account or _account()
        directory.accounts[discord_id] = account
        resolve(resolver, discord_id)
        return account

    def test_temporary_to_formal_moves_data(self, resolver, repo, directory):
        temporary = resolve(resolver)
        repo.create_music_playlist(temporary.user_id, "mine")
        repo.session.add(LinkedAccount(user_id=temporary.user_id, platform=PlatformType.Minecraft, external_id="mc-1"))
        repo.commit()
        account = _account()
        directory.accounts[DISCORD_ID] = account
        expire(repo)

        identity = resolve(resolver)

        assert identity.user_id == account.account_id and identity.is_formal
        assert _names(repo, account.account_id) == ["mine"]
        assert _names(repo, temporary.user_id) == []
        assert repo.get_linked_account(account.account_id, PlatformType.Minecraft).external_id == "mc-1"
        assert directory.account_calls == 0

    def test_absorbed_account_moves_data_and_repoints_sibling_records(self, resolver, repo, directory):
        a = self._formal(resolver, directory)
        self._formal(resolver, directory, D2, account=a)
        repo.create_music_playlist(a.account_id, "mine")
        survivor = _account()
        directory.accounts[D2] = survivor
        directory.by_account_id[a.account_id] = ResolvedAccount(survivor, merged_from=a.account_id)
        expire(repo, D2)

        identity = resolve(resolver, D2)

        assert identity.user_id == survivor.account_id
        assert _names(repo, survivor.account_id) == ["mine"]
        assert _names(repo, a.account_id) == []
        assert repo.get_discord_identity(DISCORD_ID).user_id == survivor.account_id

    def test_repointed_to_another_account_moves_nothing(self, resolver, repo, directory):
        a = self._formal(resolver, directory)
        self._formal(resolver, directory, D2, account=a)
        b = _account()
        repo.create_music_playlist(a.account_id, "a's")
        repo.create_music_playlist(b.account_id, "b's")
        directory.accounts[D2] = b
        directory.by_account_id[a.account_id] = ResolvedAccount(a)  # 舊域民仍存在，沒有 mergedFrom
        expire(repo, D2)

        identity = resolve(resolver, D2)

        assert identity.user_id == b.account_id
        assert _names(repo, a.account_id) == ["a's"]
        assert _names(repo, b.account_id) == ["b's"]
        assert repo.get_discord_identity(DISCORD_ID).user_id == a.account_id
        assert repo.get_discord_identity(D2).user_id == b.account_id

    def test_previous_account_deleted_repoints_and_logs(self, resolver, repo, directory, caplog):
        a = self._formal(resolver, directory)
        b = _account()
        repo.create_music_playlist(a.account_id, "a's")
        directory.accounts[DISCORD_ID] = b  # by_account_id 沒有 a，視為已刪除
        expire(repo)

        with caplog.at_level("WARNING", logger="starlib.identity.resolver"):
            identity = resolve(resolver)

        assert identity.user_id == b.account_id
        assert _names(repo, a.account_id) == ["a's"]
        assert _names(repo, b.account_id) == []
        assert any("no longer exists" in r.message and r.old_id == str(a.account_id) for r in caplog.records)

    def test_absorbed_into_different_account_moves_nothing(self, resolver, repo, directory):
        a = self._formal(resolver, directory)
        repo.create_music_playlist(a.account_id, "a's")
        c, d = _account(), _account()
        directory.accounts[DISCORD_ID] = d
        directory.by_account_id[a.account_id] = ResolvedAccount(c, merged_from=a.account_id)
        expire(repo)

        identity = resolve(resolver)

        assert identity.user_id == d.account_id
        assert _names(repo, a.account_id) == ["a's"]
        assert _names(repo, d.account_id) == []

    def test_cannot_check_previous_account_keeps_record_and_backs_off(self, resolver, repo, directory):
        a = self._formal(resolver, directory)
        repo.create_music_playlist(a.account_id, "a's")
        directory.accounts[DISCORD_ID] = _account()
        directory.account_unavailable = True
        expire(repo)

        identity = resolve(resolver)
        resolve(resolver)

        assert identity.user_id == a.account_id
        assert repo.get_discord_identity(DISCORD_ID).user_id == a.account_id
        assert _names(repo, a.account_id) == ["a's"]
        assert directory.account_calls == 1  # 第二次在 backoff 內，不再等逾時

        directory.account_unavailable = False
        resolver._unavailable_until = None
        assert resolve(resolver).user_id == directory.accounts[DISCORD_ID].account_id

    def test_failed_move_keeps_data_and_record(self, resolver, repo, directory, monkeypatch):
        temporary = resolve(resolver)
        repo.create_music_playlist(temporary.user_id, "mine")
        directory.accounts[DISCORD_ID] = _account()
        expire(repo)
        monkeypatch.setattr(SQLRepository, "_merge_user_data", lambda self, o, n: (_ for _ in ()).throw(RuntimeError("bug")))

        identity = resolve(resolver)

        assert identity == temporary
        record = repo.get_discord_identity(DISCORD_ID)
        assert record.user_id == temporary.user_id and not record.is_formal
        assert _names(repo, temporary.user_id) == ["mine"]

        # 下次使用再試，這次成功就搬過去（先過 backoff）
        monkeypatch.undo()
        resolver._merge_retry_after.clear()
        retried = resolve(resolver)
        assert retried.user_id == directory.accounts[DISCORD_ID].account_id
        assert _names(repo, retried.user_id) == ["mine"]

    def test_failed_move_backs_off_only_that_user(self, resolver, repo, directory, monkeypatch):
        temporary = resolve(resolver)
        other = resolve(resolver, D2)
        directory.accounts[DISCORD_ID] = _account()
        directory.accounts[D2] = _account()
        expire(repo)
        expire(repo, D2)
        monkeypatch.setattr(SQLRepository, "_merge_user_data", lambda self, o, n: (_ for _ in ()).throw(RuntimeError("bug")))

        resolve(resolver)
        calls = directory.calls
        again = resolve(resolver)  # backoff 內：不打 auth server、不重跑搬資料

        assert again == temporary
        assert directory.calls == calls
        # 別人不受影響：照常查 auth server，（搬資料同樣失敗）但不是被擋在 backoff 外
        resolve(resolver, D2)
        assert directory.calls == calls + 1
        assert other.user_id == repo.get_discord_identity(D2).user_id

    def test_backoff_expires_and_success_clears_it(self, directory, repo):
        resolver = IdentityResolver(directory, repo, TTL, merge_backoff=timedelta(0))
        temporary = resolve(resolver)
        directory.accounts[DISCORD_ID] = _account()
        expire(repo)
        resolver._merge_retry_after[DISCORD_ID] = nowtz() - timedelta(seconds=1)

        identity = resolve(resolver)

        assert identity.user_id != temporary.user_id and identity.is_formal
        assert DISCORD_ID not in resolver._merge_retry_after


class TestTemporaryIdentityRace:
    def test_second_insert_keeps_first_id(self, repo):
        first = uuid4()
        repo.create_temporary_discord_identity(DISCORD_ID, first, nowtz())
        record = repo.create_temporary_discord_identity(DISCORD_ID, uuid4(), nowtz())

        assert record.user_id == first


# ─── auth server adapter ────────────────────────────────────────────────────


async def _with_server(handler, call, twitch_provider: str = "twitch"):
    app = web.Application()
    app.router.add_get("/v1/passports/{provider}/{id}", handler)
    app.router.add_get("/v1/accounts/{id}", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    try:
        return await call(DomalyzeIdentityClient(f"http://127.0.0.1:{port}/", "key", timeout=0.5, twitch_provider=twitch_provider))
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

    def test_foreign_404_is_unavailable(self):
        async def handler(request):
            return web.json_response({"detail": "Not Found"}, status=404)

        with pytest.raises(DirectoryUnavailable):
            _find(handler)

    def test_404_without_json_is_unavailable(self):
        async def handler(request):
            return web.Response(status=404, text="<html>not found</html>")

        with pytest.raises(DirectoryUnavailable):
            _find(handler)

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

    def test_find_by_passport_encodes_path(self):
        seen = {}

        async def handler(request: web.Request):
            seen["path"] = request.raw_path
            return web.json_response({"detail": "account not found"}, status=404)

        result = asyncio.run(_with_server(handler, lambda client: client.find_by_passport("twitch", "a b/c")))

        assert result is None
        assert seen["path"] == "/v1/passports/twitch/a%20b%2Fc"

    def test_twitch_passports_only_keep_configured_provider(self):
        account_id = uuid4()
        passports = [
            {"provider": "discord", "subject": str(DISCORD_ID), "username": "w"},
            {"provider": "twitch-main", "subject": "111", "username": "WillyTV"},
            {"provider": "twitch-main", "subject": "222", "username": None},
            {"provider": "twitch", "subject": "333", "username": "other"},
        ]

        async def handler(request):
            return web.json_response({"accountId": str(account_id), "roles": [], "suspended": False, "passports": passports})

        account = asyncio.run(_with_server(handler, lambda client: client.find_by_discord(DISCORD_ID), twitch_provider="twitch-main"))

        assert account.twitch_passports == (LinkedPassport("111", "WillyTV"), LinkedPassport("222", None))

    def test_missing_passports_is_empty(self):
        async def handler(request):
            return web.json_response({"accountId": str(uuid4()), "roles": [], "suspended": False})

        assert _find(handler).twitch_passports == ()

    @pytest.mark.parametrize("passports", [[{"subject": "1"}], ["twitch"], 5])
    def test_malformed_passports_is_unavailable(self, passports):
        async def handler(request):
            return web.json_response({"accountId": str(uuid4()), "passports": passports})

        with pytest.raises(DirectoryUnavailable):
            _find(handler)


def _find_account(handler, account_id: UUID):
    return asyncio.run(_with_server(handler, lambda client: client.find_by_account_id(account_id)))


class TestFindByAccountId:
    def test_live_account_has_no_merged_from(self):
        account_id = uuid4()
        seen = {}

        async def handler(request: web.Request):
            seen["auth"] = request.headers.get("Authorization")
            seen["id"] = request.match_info["id"]
            return web.json_response({"accountId": str(account_id), "username": "willy", "roles": ["admin"], "suspended": False, "isAdmin": True})

        result = _find_account(handler, account_id)

        assert result == ResolvedAccount(Account(account_id=account_id, username="willy", roles=("admin",), suspended=False))
        assert result.merged_from is None
        assert seen == {"auth": "Bearer key", "id": str(account_id)}

    def test_absorbed_id_returns_survivor_with_merged_from(self):
        old_id, survivor_id = uuid4(), uuid4()

        async def handler(request):
            return web.json_response({"accountId": str(survivor_id), "username": "w", "roles": [], "suspended": False, "mergedFrom": str(old_id)})

        result = _find_account(handler, old_id)

        assert result.account.account_id == survivor_id
        assert result.merged_from == old_id

    def test_not_found(self):
        async def handler(request):
            return web.json_response({"detail": "account not found"}, status=404)

        assert _find_account(handler, uuid4()) is None

    def test_foreign_404_is_unavailable(self):
        async def handler(request):
            return web.json_response({"detail": "Not Found"}, status=404)

        with pytest.raises(DirectoryUnavailable):
            _find_account(handler, uuid4())

    @pytest.mark.parametrize("status", [401, 500, 503])
    def test_error_status_is_unavailable(self, status):
        async def handler(request):
            return web.json_response({}, status=status)

        with pytest.raises(DirectoryUnavailable):
            _find_account(handler, uuid4())

    @pytest.mark.parametrize("body", [{}, {"accountId": "not-a-uuid"}, {"accountId": str(uuid4()), "mergedFrom": "bad"}, [1]])
    def test_malformed_is_unavailable(self, body):
        async def handler(request):
            return web.json_response(body)

        with pytest.raises(DirectoryUnavailable):
            _find_account(handler, uuid4())

    def test_connection_refused_is_unavailable(self):
        client = DomalyzeIdentityClient("http://127.0.0.1:9", "key", timeout=0.5)

        with pytest.raises(DirectoryUnavailable):
            asyncio.run(client.find_by_account_id(uuid4()))
