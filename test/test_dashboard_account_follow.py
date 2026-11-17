"""後台 session 的析域帳號跟隨：Discord 登入時反查、每 60 秒重新確認、auth server 不可用時沿用（假 auth server，真實 PostgreSQL）。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlmodel import select
from test_dashboard_auth import (  # noqa: F401  (fixture 與 helper)
    USER_ID,
    dashboard_env,
    login,
    make_app,
    make_session,
    spy,
)
from test_identity import repo  # noqa: F401

from starlib.database import DashboardSession
from starlib.identity import Account, LinkedPassport
from starServer.dashboard import session
from starServer.dashboard.session import SessionInfo, require_session

OTHER_DISCORD = 99


def account(username="willy", discord_ids=(int(USER_ID),), suspended=False, account_id=None) -> Account:
    return Account(
        account_id=account_id or uuid4(),
        username=username,
        roles=(),
        suspended=suspended,
        discord_passports=tuple(LinkedPassport(str(i), None) for i in discord_ids),
    )


class Clock:
    def __init__(self):
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch) -> Clock:
    c = Clock()
    monkeypatch.setattr(session, "time", SimpleNamespace(monotonic=c.monotonic))
    return c


@pytest.fixture
def directory(dashboard_env):
    return dashboard_env.directory


@pytest.fixture
def client(repo, clock) -> TestClient:  # noqa: F811
    app = make_app()

    @app.get("/dashboard/probe-session")
    async def probe(info: SessionInfo = Depends(require_session)):
        return {
            "account_id": None if info.account_id is None else str(info.account_id),
            "username": info.account_username,
            "discord_ids": list(info.discord_ids),
            "stale": info.stale,
        }

    c = TestClient(app, base_url="https://testserver", follow_redirects=False)
    make_session(repo)
    c.cookies.set("dashboard_session", "sid")
    return c


def me(client):
    return client.get("/dashboard/me").json()["account"]


def probe(client):
    return client.get("/dashboard/probe-session").json()


def db_account_id(repo, session_id="sid"):  # noqa: F811
    repo.session.expire_all()
    return repo.session.get(DashboardSession, session_id, populate_existing=True).account_id


class TestLogin:
    def test_linked_discord_login_carries_account(self, repo, spy, directory, clock):  # noqa: F811
        acc = account()
        directory.accounts[int(USER_ID)] = acc
        c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
        login(c, spy)
        assert me(c) == {"username": "willy"}
        row = repo.session.exec(select(DashboardSession).where(DashboardSession.discord_user_id == USER_ID)).one()
        assert row.account_id == acc.account_id and row.via_domalyze is False

    def test_unlinked_discord_login_has_no_account(self, spy, clock):
        c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
        login(c, spy)
        assert me(c) is None

    def test_login_succeeds_when_auth_server_down(self, spy, directory, clock):
        directory.unavailable = True
        c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
        r = login(c, spy)
        assert r.status_code == 307
        assert me(c) is None


class TestFollow:
    def test_fields(self, client, directory):
        acc = account(discord_ids=(OTHER_DISCORD, int(USER_ID)))
        directory.accounts[int(USER_ID)] = acc
        assert probe(client) == {
            "account_id": str(acc.account_id),
            "username": "willy",
            "discord_ids": [OTHER_DISCORD, int(USER_ID)],
            "stale": False,
        }

    def test_rechecks_only_after_60_seconds(self, client, directory, clock, repo):  # noqa: F811
        assert me(client) is None
        acc = account()
        directory.accounts[int(USER_ID)] = acc  # 登入後才連結
        clock.now += 59
        assert me(client) is None
        assert directory.calls == 1
        clock.now += 2
        assert me(client) == {"username": "willy"}
        assert directory.calls == 2
        assert db_account_id(repo) == acc.account_id

    @pytest.mark.parametrize("change", ["suspended", "unlinked"])
    def test_suspended_or_unlinked_drops_account(self, client, directory, clock, repo, change):  # noqa: F811
        directory.accounts[int(USER_ID)] = account()
        assert me(client) == {"username": "willy"}
        if change == "suspended":
            directory.accounts[int(USER_ID)] = account(suspended=True)
        else:
            del directory.accounts[int(USER_ID)]
        clock.now += 61
        assert me(client) is None
        assert client.get("/dashboard/me").status_code == 200  # session 照常可用
        assert db_account_id(repo) is None

    def test_merge_follows_survivor(self, client, directory, clock, repo):  # noqa: F811
        directory.accounts[int(USER_ID)] = account(username="old")
        assert me(client) == {"username": "old"}
        survivor = account(username="survivor")
        directory.accounts[int(USER_ID)] = survivor
        clock.now += 61
        assert me(client) == {"username": "survivor"}
        assert db_account_id(repo) == survivor.account_id

    def test_unavailable_keeps_previous_and_backs_off(self, client, directory, clock):
        acc = account(discord_ids=(OTHER_DISCORD, int(USER_ID)))
        directory.accounts[int(USER_ID)] = acc
        probe(client)
        directory.unavailable = True
        clock.now += 61
        result = probe(client)
        assert result["account_id"] == str(acc.account_id) and result["username"] == "willy"
        assert result["discord_ids"] == [OTHER_DISCORD, int(USER_ID)] and result["stale"] is True
        calls = directory.calls
        clock.now += 30
        probe(client)
        clock.now += 20  # 距離失敗 50 秒，仍在 backoff 內
        probe(client)
        assert directory.calls == calls

    def test_unavailable_after_restart_uses_db_account(self, client, directory, repo, monkeypatch):  # noqa: F811
        acc_id = uuid4()
        row = repo.session.get(DashboardSession, "sid")
        row.account_id = acc_id
        repo.session.add(row)
        repo.session.commit()
        directory.unavailable = True
        assert probe(client) == {
            "account_id": str(acc_id),
            "username": None,
            "discord_ids": [int(USER_ID)],
            "stale": True,
        }
        assert me(client) == {"username": None}
        assert db_account_id(repo) == acc_id

    def test_unavailable_without_account_stays_empty(self, client, directory):
        directory.unavailable = True
        assert probe(client) == {"account_id": None, "username": None, "discord_ids": [], "stale": True}


class TestFollowedLifecycle:
    def test_concurrent_requests_share_one_check(self, directory, clock):
        calls = []

        async def slow_find(discord_id):
            calls.append(discord_id)
            await asyncio.sleep(0.05)
            return None

        directory.find_by_discord = slow_find
        info = SessionInfo("sid", USER_ID, "n", None)

        async def run():
            return await asyncio.gather(*(session.follow_account(info) for _ in range(3)))

        results = asyncio.run(run())
        assert len(calls) == 1
        assert all(r.account_id is None for r in results)
        assert session._inflight == {}

    def test_logout_clears_followed(self, client, repo):  # noqa: F811
        make_session(repo, session_id="other-device")
        probe(client)
        session._followed["other-device"] = session._followed["sid"]
        assert client.post("/dashboard/logout", headers={"Origin": "https://domalyze.net"}).status_code == 200
        assert "sid" not in session._followed and "other-device" not in session._followed

    def test_stale_entries_pruned_on_login(self, repo, spy, clock):  # noqa: F811
        session._followed["long-gone"] = session._Followed(
            clock.now - session.SESSION_TTL.total_seconds() - 1, None, None, (), False
        )
        session._followed["recent"] = session._Followed(clock.now, None, None, (), False)
        c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
        login(c, spy)
        assert "long-gone" not in session._followed and "recent" in session._followed

    def test_logout_during_check_does_not_restore_entry(self, repo, directory, clock):  # noqa: F811
        make_session(repo)

        async def find_then_logout(discord_id):
            await asyncio.to_thread(session.delete_user_sessions, USER_ID)
            return None

        directory.find_by_discord = find_then_logout
        asyncio.run(session.follow_account(SessionInfo("sid", USER_ID, "n", None)))
        assert "sid" not in session._followed
