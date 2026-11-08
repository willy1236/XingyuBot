"""伺服器管理後台 T-09：從清單邀請 bot（假 Discord，真實 PostgreSQL）。"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select
from test_dashboard_auth import (  # noqa: F401  (fixture 與 helper)
    FRONTEND,
    ORIGINS,
    STATE,
    USER_ID,
    dashboard_env,
    encode_cookie,
    make_app,
    make_session,
    set_cookies,
    spy,
)
from test_dashboard_guilds import MANAGE_CHANNELS, MANAGE_GUILD, g
from test_dashboard_guilds import discord as discord_env  # noqa: F401  (fixture)
from test_identity import repo  # noqa: F401

from starlib import sclient
from starlib.database import DashboardSession, OAuthToken
from starlib.oauth.models import DiscordUser
from starServer.dashboard import invite

GUILD = "1001"
OTHER_USER = "222222222222222222"


class FakeBot:
    def __init__(self, guild_ids=(), ready=True):
        self.guilds_ids = set(guild_ids)
        self.ready = ready

    def is_ready(self):
        return self.ready

    @property
    def guilds(self):
        from types import SimpleNamespace

        return [SimpleNamespace(id=int(i)) for i in self.guilds_ids]

    def submit(self, coro):
        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        return ThreadPoolExecutor(max_workers=1).submit(asyncio.run, coro)


@pytest.fixture
def env(monkeypatch, spy, discord_env, repo, dashboard_env):  # noqa: F811
    monkeypatch.setattr(invite, "WAIT_SECONDS", 0.3)
    monkeypatch.setattr(invite, "POLL_INTERVAL", 0.05)
    monkeypatch.setattr(sclient, "bot", FakeBot({GUILD}))
    discord_env.guilds = [g(GUILD, "guild", MANAGE_GUILD | MANAGE_CHANNELS)]
    return spy


def client_with_session(repo, user_id=USER_ID) -> TestClient:  # noqa: F811
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
    make_session(repo, user_id=user_id)
    c.cookies.set("dashboard_session", "sid")
    return c


def callback(client: TestClient, guild_id: str | None = GUILD, **params):
    client.cookies.set("dashboard_oauth", encode_cookie(purpose="invite", next="/dashboard"))
    query = {"code": "c", "state": STATE, **params}
    if guild_id:
        query["guild_id"] = guild_id
    return client.get("/oauth/discord", params=query)


class TestInviteEntry:
    def test_redirects_to_discord_with_preselected_guild(self, env, repo, dashboard_env):  # noqa: F811
        c = client_with_session(repo)
        res = c.get("/to/dashboard-invite", params={"guild_id": GUILD, "origin": FRONTEND})
        assert res.status_code in (302, 307)
        q = parse_qs(urlparse(res.headers["location"]).query)
        assert q["guild_id"] == [GUILD] and q["disable_guild_select"] == ["false"]
        assert q["permissions"] == ["8"]
        assert set(q["scope"][0].split()) == {"bot", "identify", "guilds"}
        assert "dashboard_oauth=" in "".join(set_cookies(res))

    def test_without_guild_id_has_no_preselect(self, env, repo, dashboard_env):  # noqa: F811
        c = client_with_session(repo)
        q = parse_qs(urlparse(c.get("/to/dashboard-invite").headers["location"]).query)
        assert "guild_id" not in q

    def test_invalid_guild_id_is_ignored(self, env, repo, dashboard_env):  # noqa: F811
        c = client_with_session(repo)
        q = parse_qs(urlparse(c.get("/to/dashboard-invite", params={"guild_id": "x&y"}).headers["location"]).query)
        assert "guild_id" not in q

    def test_state_cookie_has_invite_purpose(self, env, repo, dashboard_env):  # noqa: F811
        import base64
        import json

        c = client_with_session(repo)
        res = c.get("/to/dashboard-invite", params={"origin": "https://www.domalyze.net"})
        raw = set_cookies(res)[0].split("dashboard_oauth=")[1].split(";")[0]
        cookie = json.loads(base64.urlsafe_b64decode(raw.encode()))
        assert cookie["purpose"] == "invite" and cookie["origin"] == "https://www.domalyze.net"

    def test_without_session_goes_to_login_then_list(self, env, dashboard_env):  # noqa: F811
        c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
        res = c.get("/to/dashboard-invite", params={"origin": FRONTEND})
        loc = urlparse(res.headers["location"])
        assert loc.path == "/to/dashboard-login"
        assert parse_qs(loc.query) == {"next": ["/dashboard"], "origin": [FRONTEND]}


class TestInviteCallback:
    def test_manager_goes_to_notify_page(self, env, repo, dashboard_env):  # noqa: F811
        res = callback(client_with_session(repo))
        assert res.headers["location"] == f"{FRONTEND}/dashboard/guilds/{GUILD}"
        assert env.saved == [USER_ID]

    def test_manage_guild_only_gets_notice(self, env, repo, discord_env, dashboard_env):  # noqa: F811
        discord_env.guilds = [g(GUILD, "guild", MANAGE_GUILD)]
        res = callback(client_with_session(repo))
        assert res.headers["location"] == f"{FRONTEND}/dashboard?notice=need_manage_channels"

    def test_actual_guild_wins_when_user_changed_selection(self, env, repo, discord_env, dashboard_env):  # noqa: F811
        discord_env.guilds = [g("2002", "other", MANAGE_GUILD | MANAGE_CHANNELS)]
        sclient.bot = FakeBot({"2002"})
        res = callback(client_with_session(repo), guild_id="2002")
        assert res.headers["location"] == f"{FRONTEND}/dashboard/guilds/2002"

    def test_cancel_goes_to_list(self, env, repo, dashboard_env):  # noqa: F811
        c = client_with_session(repo)
        c.cookies.set("dashboard_oauth", encode_cookie(purpose="invite", next="/dashboard"))
        res = c.get("/oauth/discord", params={"error": "access_denied", "state": STATE})
        assert res.headers["location"] == f"{FRONTEND}/dashboard"
        assert env.saved == []

    def test_cache_is_refreshed_after_invite(self, env, repo, discord_env, dashboard_env):  # noqa: F811
        from starServer.dashboard import guilds

        guilds._cache[USER_ID] = (10**12, [])
        callback(client_with_session(repo))
        assert guilds._cache[USER_ID][1] != []

    def test_bot_not_visible_yet_shows_pending(self, env, repo, dashboard_env):  # noqa: F811
        sclient.bot = FakeBot(set())
        res = callback(client_with_session(repo))
        assert res.headers["location"] == f"{FRONTEND}/dashboard?notice=invite_pending"

    def test_bot_not_ready_shows_pending(self, env, repo, dashboard_env):  # noqa: F811
        sclient.bot = FakeBot({GUILD}, ready=False)
        res = callback(client_with_session(repo))
        assert res.headers["location"] == f"{FRONTEND}/dashboard?notice=invite_pending"

    def test_without_guild_id_goes_to_list(self, env, repo, dashboard_env):  # noqa: F811
        res = callback(client_with_session(repo), guild_id=None)
        assert res.headers["location"] == f"{FRONTEND}/dashboard"

    def test_different_account_switches_session_and_goes_to_list(self, env, repo, dashboard_env):  # noqa: F811
        env.user = DiscordUser(id=OTHER_USER, username="other", global_name=None, avatar=None)
        c = client_with_session(repo)
        res = callback(c)
        assert res.headers["location"] == f"{FRONTEND}/dashboard"
        assert "dashboard_session=" in "".join(set_cookies(res))
        repo.session.expire_all()
        rows = repo.session.exec(select(DashboardSession)).all()
        assert [r.discord_user_id for r in rows] == [OTHER_USER]
        assert repo.session.get(OAuthToken, (OTHER_USER, dashboard_env.credential_id)) is not None

    def test_no_session_creates_one_and_continues(self, env, repo, dashboard_env):  # noqa: F811
        c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
        res = callback(c)
        assert res.headers["location"] == f"{FRONTEND}/dashboard/guilds/{GUILD}"
        assert "dashboard_session=" in "".join(set_cookies(res))
        repo.session.expire_all()
        assert [r.discord_user_id for r in repo.session.exec(select(DashboardSession)).all()] == [USER_ID]

    def test_same_account_keeps_session(self, env, repo, dashboard_env):  # noqa: F811
        res = callback(client_with_session(repo))
        assert "dashboard_session=" not in "".join(set_cookies(res))

    def test_exchange_failure(self, env, repo, dashboard_env):  # noqa: F811
        env.exchange_error = RuntimeError("bad")
        res = callback(client_with_session(repo))
        assert res.status_code == 400

    def test_oauth_cookie_cleared(self, env, repo, dashboard_env):  # noqa: F811
        res = callback(client_with_session(repo))
        assert any(c.startswith("dashboard_oauth=") and "Max-Age=0" in c for c in set_cookies(res))


def test_origins_fixture_sanity():
    assert FRONTEND in ORIGINS
