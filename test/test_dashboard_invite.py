"""伺服器管理後台：從後台經統一邀請流程邀請 bot（假 bot，真實 PostgreSQL）。"""

from __future__ import annotations

import asyncio
import base64
import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
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
    site,
    spy,
)
from test_dashboard_guilds import MANAGE_CHANNELS, MANAGE_GUILD, g
from test_dashboard_guilds import discord as discord_env  # noqa: F401  (fixture)
from test_identity import repo  # noqa: F401

from starlib import sclient
from starlib.database import DashboardSession, OAuthToken
from starlib.oauth import DiscordOAuth
from starServer.dashboard import invite

GUILD = "1001"
OTHER_USER = "222222222222222222"


class FakeBot:
    def __init__(self, guild_ids=(), ready=True):
        self.guilds_ids = set(guild_ids)
        self.ready = ready
        self._pool = ThreadPoolExecutor(max_workers=1)

    def is_ready(self):
        return self.ready

    @property
    def guilds(self):
        return [SimpleNamespace(id=int(i)) for i in self.guilds_ids]

    def get_guild(self, gid):
        return SimpleNamespace(id=gid) if str(gid) in self.guilds_ids else None

    def submit(self, coro):
        return self._pool.submit(asyncio.run, coro)


@pytest.fixture
def env(monkeypatch, discord_env, repo, dashboard_env):  # noqa: F811
    monkeypatch.setattr(invite, "WAIT_SECONDS", 0.3)
    monkeypatch.setattr(invite, "POLL_INTERVAL", 0.05)
    monkeypatch.setattr(sclient, "bot", FakeBot({GUILD}))
    discord_env.guilds = [g(GUILD, "guild", MANAGE_GUILD | MANAGE_CHANNELS)]

    async def must_not_exchange(self, code):
        raise AssertionError("後台邀請不該交換 code")

    monkeypatch.setattr(DiscordOAuth, "exchange_code", must_not_exchange)


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


def oauth_cookie(response) -> dict:
    raw = next(c for c in set_cookies(response) if c.startswith("dashboard_oauth="))
    return json.loads(base64.urlsafe_b64decode(raw.split("dashboard_oauth=")[1].split(";")[0].encode()))


# ====== 統一邀請入口 /to/discordbot ======
class TestInviteEntry:
    def test_from_dashboard_writes_invite_cookie(self, site):
        res = site.get("/to/discordbot", params={"origin": "https://www.domalyze.net"})
        assert res.status_code == 307
        q = parse_qs(urlparse(res.headers["location"]).query)
        assert set(q["scope"][0].split()) == {"bot", "identify", "applications.commands.permissions.update"}
        assert q["permissions"] == ["8"]
        assert "guild_id" not in q  # 由使用者在 Discord 邀請頁選擇伺服器
        cookie = oauth_cookie(res)
        assert (cookie["purpose"], cookie["next"], cookie["origin"]) == (
            "invite",
            "/dashboard",
            "https://www.domalyze.net",
        )
        assert cookie["state"] == q["state"][0]
        assert "oauth_state=" not in "".join(set_cookies(res))

    def test_unknown_origin_falls_back_to_frontend(self, site):
        res = site.get("/to/discordbot", params={"origin": "https://evil.example"})
        assert oauth_cookie(res)["origin"] == FRONTEND

    def test_without_origin_unchanged(self, site):
        res = site.get("/to/discordbot")
        assert res.status_code == 307
        cookies = "".join(set_cookies(res))
        assert "oauth_state=" in cookies and "dashboard_oauth=" not in cookies

    def test_dashboard_invite_removed(self, site):
        assert site.get("/to/dashboard-invite").status_code == 404


# ====== 回到 /oauth/discord ======
class TestInviteCallback:
    def test_manager_goes_to_guild_page(self, env, repo):  # noqa: F811
        res = callback(client_with_session(repo))
        assert res.headers["location"] == f"{FRONTEND}/dashboard/guilds/{GUILD}"

    @pytest.mark.parametrize("permissions", [MANAGE_GUILD, 0x4, 0x10000000])  # Manage Server、Ban、Manage Roles
    def test_any_entry_permission_goes_to_guild_page(self, env, repo, discord_env, permissions):  # noqa: F811
        discord_env.guilds = [g(GUILD, "guild", permissions)]
        res = callback(client_with_session(repo))
        assert res.headers["location"] == f"{FRONTEND}/dashboard/guilds/{GUILD}"

    def test_without_entry_permission_gets_notice(self, env, repo, discord_env):  # noqa: F811
        discord_env.guilds = [g(GUILD, "guild", 0x400)]  # 只有 View Channel
        res = callback(client_with_session(repo))
        assert res.headers["location"] == f"{FRONTEND}/dashboard/guilds?notice=need_permissions"

    def test_actual_guild_wins(self, env, repo, discord_env):  # noqa: F811
        discord_env.guilds = [g("2002", "other", MANAGE_GUILD | MANAGE_CHANNELS)]
        sclient.bot = FakeBot({"2002"})
        res = callback(client_with_session(repo), guild_id="2002")
        assert res.headers["location"] == f"{FRONTEND}/dashboard/guilds/2002"

    def test_cancel_goes_to_list(self, env, repo):  # noqa: F811
        c = client_with_session(repo)
        c.cookies.set("dashboard_oauth", encode_cookie(purpose="invite", next="/dashboard"))
        res = c.get("/oauth/discord", params={"error": "access_denied", "state": STATE})
        assert res.headers["location"] == f"{FRONTEND}/dashboard/guilds"

    def test_bot_not_visible_yet_shows_pending(self, env, repo):  # noqa: F811
        sclient.bot = FakeBot(set())
        res = callback(client_with_session(repo))
        assert res.headers["location"] == f"{FRONTEND}/dashboard/guilds?notice=invite_pending"

    def test_bot_not_ready_shows_pending(self, env, repo):  # noqa: F811
        sclient.bot = FakeBot({GUILD}, ready=False)
        res = callback(client_with_session(repo))
        assert res.headers["location"] == f"{FRONTEND}/dashboard/guilds?notice=invite_pending"

    def test_without_guild_id_goes_to_list(self, env, repo):  # noqa: F811
        res = callback(client_with_session(repo), guild_id=None)
        assert res.headers["location"] == f"{FRONTEND}/dashboard/guilds"

    def test_session_account_decides_and_session_unchanged(self, env, repo, discord_env):  # noqa: F811
        """Discord 邀請頁登入哪個帳號都不影響：以 session 的帳號判斷權限，session 不換。"""
        c = client_with_session(repo, user_id=OTHER_USER)
        discord_env.guilds = [g(GUILD, "guild", 0x400)]
        res = callback(c)
        assert res.headers["location"] == f"{FRONTEND}/dashboard/guilds?notice=need_permissions"
        assert "dashboard_session=" not in "".join(set_cookies(res))
        repo.session.expire_all()
        assert repo.session.get(DashboardSession, "sid", populate_existing=True).discord_user_id == OTHER_USER

    def test_no_session_goes_to_login(self, env, repo):  # noqa: F811
        c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
        res = callback(c)
        assert res.headers["location"] == f"{FRONTEND}/dashboard-login?next=%2Fdashboard%2Fguilds"
        assert "dashboard_session=" not in "".join(set_cookies(res))

    def test_no_token_saved(self, env, repo, dashboard_env):  # noqa: F811
        callback(client_with_session(repo))
        rows = repo.session.exec(
            select(OAuthToken).where(
                OAuthToken.client_credential_id == dashboard_env.credential_id, OAuthToken.user_id == USER_ID
            )
        ).all()
        assert rows == []

    def test_oauth_cookie_cleared(self, env, repo):  # noqa: F811
        res = callback(client_with_session(repo))
        assert any(c.startswith("dashboard_oauth=") and "Max-Age=0" in c for c in set_cookies(res))


def test_origins_fixture_sanity():
    assert FRONTEND in ORIGINS
