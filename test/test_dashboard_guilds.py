"""伺服器管理後台 T-02：伺服器清單、權限判斷、快取與 token refresh（假 Discord，真實 PostgreSQL）。"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace

import httpx
import pytest
from authlib.integrations.base_client.errors import OAuthError
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

from starlib import sclient
from starlib.database import OAuthToken
from starlib.oauth import DiscordOAuth, oauth_lib
from starlib.utils import nowtz
from starServer.dashboard import auth, guilds
from starServer.dashboard.errors import DashboardError

ADMIN = 0x8
MANAGE_CHANNELS = 0x10
MANAGE_GUILD = 0x20


def g(gid: str, name: str, permissions: int = 0, owner: bool = False, icon: str | None = None) -> dict:
    return {"id": gid, "name": name, "icon": icon, "owner": owner, "permissions": str(permissions)}


class FakeDiscord:
    def __init__(self):
        self.guilds: list[dict] = []
        self.calls = 0
        self.error: Exception | None = None
        self.delay = 0.0


@pytest.fixture
def discord(monkeypatch, dashboard_env, repo) -> FakeDiscord:  # noqa: F811
    fake = FakeDiscord()
    monkeypatch.setattr(guilds, "sqldb", repo)
    monkeypatch.setattr(oauth_lib, "sqldb", repo)  # save_token_to_db 用的
    guilds._cache.clear()
    auth._user_locks.clear()

    async def api_get(self, path, params=None):
        assert path == "/users/@me/guilds"
        fake.calls += 1
        if fake.delay:
            await asyncio.sleep(fake.delay)
        if fake.error:
            raise fake.error
        return list(fake.guilds)

    monkeypatch.setattr(DiscordOAuth, "api_get", api_get)
    return fake


def seed_token(repo, credential_id, *, scope=("identify", "guilds"), expires_in=timedelta(days=7), user_id=USER_ID):  # noqa: F811
    repo.merge(
        OAuthToken(
            user_id=user_id,
            client_credential_id=credential_id,
            access_token="access-old",
            refresh_token="refresh-old",
            scope=list(scope),
            expires_at=nowtz() + expires_in,
        )
    )


@pytest.fixture
def token(repo, dashboard_env):  # noqa: F811
    seed_token(repo, dashboard_env.credential_id)


def http_error(status: int) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "https://discord.com")
    return httpx.HTTPStatusError("x", request=req, response=httpx.Response(status, request=req))


def fake_bot(ids: list[int], ready: bool = True):
    pool = ThreadPoolExecutor(max_workers=1)
    return SimpleNamespace(
        is_ready=lambda: ready,
        guilds=[SimpleNamespace(id=i) for i in ids],
        submit=lambda coro: pool.submit(asyncio.run, coro),
    )


# ====== GET /dashboard/guilds ======
class TestListEndpoint:
    @pytest.fixture
    def client(self, discord, token, repo) -> TestClient:  # noqa: F811
        make_session(repo)
        c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
        c.cookies.set("dashboard_session", "sid")
        return c

    def test_groups_filter_and_sort(self, client, discord, monkeypatch):
        discord.guilds = [
            g("1", "banana", MANAGE_CHANNELS),  # 已邀請、有 Manage Channels
            g("2", "Apple", ADMIN),  # 已邀請、Administrator
            g("3", "cherry", MANAGE_GUILD),  # 已邀請但只有 Manage Server → 不出現
            g("4", "delta", MANAGE_GUILD),  # 未邀請、Manage Server
            g("5", "echo", MANAGE_CHANNELS),  # 未邀請但只有 Manage Channels → 不出現
            g("6", "foxtrot", 0, owner=True),  # 未邀請、擁有者
            g("7", "golf", 0),  # 未邀請、無權限 → 不出現
            g("8", "hotel", 0, owner=True, icon="a_abc"),  # 已邀請、擁有者
        ]
        monkeypatch.setattr(sclient, "bot", fake_bot([1, 2, 3, 8]))
        res = client.get("/dashboard/guilds")
        assert res.status_code == 200
        body = res.json()
        assert [x["name"] for x in body["invited"]] == ["Apple", "banana", "hotel"]
        assert [x["name"] for x in body["not_invited"]] == ["delta", "foxtrot"]
        assert body["invited"][2]["icon_url"] == "https://cdn.discordapp.com/icons/8/a_abc.gif"
        assert body["invited"][0]["icon_url"] is None

    def test_bot_not_ready(self, client, monkeypatch):
        monkeypatch.setattr(sclient, "bot", None)
        res = client.get("/dashboard/guilds")
        assert (res.status_code, res.json()) == (503, {"error": "bot_unavailable"})
        monkeypatch.setattr(sclient, "bot", fake_bot([], ready=False))
        assert client.get("/dashboard/guilds").json() == {"error": "bot_unavailable"}

    def test_refresh_param_skips_cache(self, client, discord, monkeypatch):
        monkeypatch.setattr(sclient, "bot", fake_bot([1]))
        discord.guilds = [g("1", "a", MANAGE_CHANNELS)]
        client.get("/dashboard/guilds")
        client.get("/dashboard/guilds")
        assert discord.calls == 1
        discord.guilds = []
        assert client.get("/dashboard/guilds?refresh=1").json()["invited"] == []
        assert discord.calls == 2

    def test_bot_membership_not_cached(self, client, discord, monkeypatch):
        discord.guilds = [g("1", "a", MANAGE_CHANNELS | MANAGE_GUILD)]
        monkeypatch.setattr(sclient, "bot", fake_bot([]))
        assert client.get("/dashboard/guilds").json()["not_invited"][0]["id"] == "1"
        monkeypatch.setattr(sclient, "bot", fake_bot([1]))
        body = client.get("/dashboard/guilds").json()
        assert body["invited"][0]["id"] == "1" and body["not_invited"] == []
        assert discord.calls == 1

    def test_reauth_required(self, client, discord, monkeypatch):
        monkeypatch.setattr(sclient, "bot", fake_bot([]))
        discord.error = http_error(401)
        res = client.get("/dashboard/guilds")
        assert (res.status_code, res.json()) == (401, {"error": "reauth_required"})

    def test_requires_session(self):
        c = TestClient(make_app(), base_url="https://testserver")
        assert c.get("/dashboard/guilds").json() == {"error": "session_expired"}


# ====== 快取與錯誤 ======
class TestService:
    def test_cache_ttl(self, discord, token):
        discord.guilds = [g("1", "a")]
        asyncio.run(guilds.get_user_guilds(USER_ID))
        asyncio.run(guilds.get_user_guilds(USER_ID))
        assert discord.calls == 1
        stamp, data = guilds._cache[USER_ID]
        guilds._cache[USER_ID] = (stamp - guilds.CACHE_TTL - 1, data)
        asyncio.run(guilds.get_user_guilds(USER_ID))
        assert discord.calls == 2

    def test_invalidate(self, discord, token):
        discord.guilds = [g("1", "a")]
        asyncio.run(guilds.get_user_guilds(USER_ID))
        guilds.invalidate(USER_ID)
        asyncio.run(guilds.get_user_guilds(USER_ID))
        assert discord.calls == 2

    def test_no_token(self, discord):
        with pytest.raises(DashboardError) as e:
            asyncio.run(guilds.get_user_guilds(USER_ID))
        assert e.value.code == "reauth_required"

    def test_token_without_guilds_scope(self, discord, repo, dashboard_env):  # noqa: F811
        seed_token(repo, dashboard_env.credential_id, scope=("identify",))
        with pytest.raises(DashboardError) as e:
            asyncio.run(guilds.get_user_guilds(USER_ID))
        assert e.value.code == "reauth_required"
        assert discord.calls == 0

    def test_reauth_not_cached_and_drops_old_cache(self, discord, token):
        discord.guilds = [g("1", "a")]
        asyncio.run(guilds.get_user_guilds(USER_ID))
        discord.error = http_error(401)
        with pytest.raises(DashboardError):
            asyncio.run(guilds.get_user_guilds(USER_ID, refresh=True))
        assert USER_ID not in guilds._cache

    @pytest.mark.parametrize("error", [http_error(429), http_error(500), httpx.ConnectError("x")])
    def test_unavailable_without_cache(self, discord, token, error):
        discord.error = error
        with pytest.raises(DashboardError) as e:
            asyncio.run(guilds.get_user_guilds(USER_ID))
        assert (e.value.status, e.value.code) == (502, "discord_unavailable")
        assert USER_ID not in guilds._cache

    def test_unavailable_uses_stale_cache(self, discord, token):
        discord.guilds = [g("1", "a")]
        asyncio.run(guilds.get_user_guilds(USER_ID))
        discord.error = http_error(429)
        result = asyncio.run(guilds.get_user_guilds(USER_ID, refresh=True))
        assert [x.id for x in result] == ["1"]

    def test_single_flight(self, discord, token):
        discord.guilds = [g("1", "a")]
        discord.delay = 0.05

        async def run():
            return await asyncio.gather(*(guilds.get_user_guilds(USER_ID) for _ in range(3)))

        asyncio.run(run())
        assert discord.calls == 1

    def test_guild_perms(self, discord, token):
        discord.guilds = [
            g("1", "a", MANAGE_CHANNELS),
            g("2", "b", MANAGE_GUILD),
            g("3", "c", ADMIN),
            g("4", "d", 0, owner=True),
            g("5", "e", 0),
        ]

        def perms(gid):
            p = asyncio.run(guilds.guild_perms(USER_ID, gid))
            return p.manage_channels, p.manage_guild

        assert perms(1) == (True, False)
        assert perms("2") == (False, True)
        assert perms(3) == (True, True)
        assert perms(4) == (True, True)
        assert perms(5) == (False, False)
        assert perms(999) == (False, False)


# ====== token refresh ======
class TestRefresh:
    @pytest.fixture
    def refresh_calls(self, monkeypatch) -> list[str]:
        calls: list[str] = []

        async def refresh(self, refresh_token):
            calls.append(refresh_token)
            return {
                "access_token": "access-new",
                "refresh_token": "refresh-new",
                "token_type": "Bearer",
                "expires_in": 604800,
                "scope": "identify guilds",  # Discord 回空白分隔字串
            }

        monkeypatch.setattr(DiscordOAuth, "refresh", refresh)
        return calls

    def test_expired_token_is_refreshed_and_saved(self, discord, repo, dashboard_env, refresh_calls):  # noqa: F811
        seed_token(repo, dashboard_env.credential_id, expires_in=timedelta(seconds=-5))
        discord.guilds = [g("1", "a")]
        asyncio.run(guilds.get_user_guilds(USER_ID))
        assert refresh_calls == ["refresh-old"]
        row = repo.session.exec(
            select(OAuthToken).where(
                OAuthToken.user_id == USER_ID, OAuthToken.client_credential_id == dashboard_env.credential_id
            )
        ).one()
        repo.session.refresh(row)
        assert row.scope == ["identify", "guilds"]  # 陣列，不是字串
        assert row.client_credential_id == dashboard_env.credential_id
        assert (row.access_token, row.refresh_token) == ("access-new", "refresh-new")
        assert row.expires_at > nowtz() + timedelta(days=6)

    def test_valid_token_not_refreshed(self, discord, token, refresh_calls):
        discord.guilds = []
        asyncio.run(guilds.get_user_guilds(USER_ID))
        assert refresh_calls == []

    def test_refresh_rejected_means_reauth(self, discord, repo, dashboard_env, monkeypatch):  # noqa: F811
        seed_token(repo, dashboard_env.credential_id, expires_in=timedelta(seconds=-5))

        async def refresh(self, refresh_token):
            raise OAuthError(error="invalid_grant")

        monkeypatch.setattr(DiscordOAuth, "refresh", refresh)
        with pytest.raises(DashboardError) as e:
            asyncio.run(guilds.get_user_guilds(USER_ID))
        assert e.value.code == "reauth_required"

    def test_refresh_network_error_is_unavailable(self, discord, repo, dashboard_env, monkeypatch):  # noqa: F811
        seed_token(repo, dashboard_env.credential_id, expires_in=timedelta(seconds=-5))

        async def refresh(self, refresh_token):
            raise httpx.ConnectError("x")

        monkeypatch.setattr(DiscordOAuth, "refresh", refresh)
        with pytest.raises(DashboardError) as e:
            asyncio.run(guilds.get_user_guilds(USER_ID))
        assert e.value.code == "discord_unavailable"

    def test_concurrent_requests_refresh_once(self, discord, repo, dashboard_env, refresh_calls):  # noqa: F811
        seed_token(repo, dashboard_env.credential_id, expires_in=timedelta(seconds=-5))
        discord.guilds = []

        async def run():
            await asyncio.gather(*(guilds.get_user_guilds(USER_ID) for _ in range(3)))

        asyncio.run(run())
        assert len(refresh_calls) == 1


# ====== 登入、登出清快取 ======
def test_logout_and_login_invalidate(discord, token, repo, spy):  # noqa: F811
    discord.guilds = [g("1", "a")]
    asyncio.run(guilds.get_user_guilds(USER_ID))
    assert USER_ID in guilds._cache

    make_session(repo)
    client = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
    client.cookies.set("dashboard_session", "sid")
    assert client.post("/dashboard/logout", headers={"Origin": "https://domalyze.net"}).status_code == 200
    assert USER_ID not in guilds._cache

    guilds._cache[USER_ID] = (0.0, [])
    login(client, spy)
    assert USER_ID not in guilds._cache
