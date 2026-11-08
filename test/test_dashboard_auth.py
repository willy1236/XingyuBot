"""伺服器管理後台 T-01：登入、session、登出、CSRF、CORS、錯誤格式（假 Discord，真實 PostgreSQL，交易結束後 rollback）。"""

from __future__ import annotations

import asyncio
import base64
import json
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlmodel import select
from test_identity import repo  # noqa: F401  (repo 為 fixture)

from starlib import sqldb as real_sqldb
from starlib.database import APIType, DashboardSession, OAuthToken
from starlib.database.postgresql.client import SQLRepository
from starlib.oauth import DiscordOAuth
from starlib.oauth.models import DiscordUser
from starlib.settings import AppSettings
from starlib.utils import nowtz
from starServer import bot_website, dashboard
from starServer.dashboard import auth, config, db, session

FRONTEND = "https://domalyze.net"
ORIGINS = ["https://domalyze.net", "https://www.domalyze.net"]
STATE = "state-abc"
USER_ID = "111111111111111111"
OTHER_ID = "222222222222222222"


@pytest.fixture(autouse=True)
def dashboard_env(monkeypatch, repo):  # noqa: F811
    monkeypatch.setattr(config, "frontend_url", lambda: FRONTEND)
    monkeypatch.setattr(config, "allowed_origins", lambda: ORIGINS)
    for module in (db, session, auth):
        monkeypatch.setattr(module, "sqldb", repo)
    # 不讀真實的 oauth client，但 credential_id 要是真的（OAuthToken 有外鍵）
    credential_id = real_sqldb.get_oauth_client(APIType.Discord, 4).credential_id
    real_sqldb.release_session()
    fake_client = SimpleNamespace(
        client_id="cid",
        client_secret="secret",
        redirect_uri="https://api.example.test/oauth/discord",
        default_scopes=["identify"],
        credential_id=credential_id,
    )
    monkeypatch.setattr(auth, "_oauth_client_cache", fake_client)
    return fake_client


class Spy:
    def __init__(self):
        self.revoked: list[str] = []
        self.revoke_error: Exception | None = None
        self.user = DiscordUser(id=USER_ID, username="someone", global_name="Some One", avatar="abc")
        self.exchange_error: Exception | None = None
        self.saved: list[str] = []


@pytest.fixture
def spy(monkeypatch, dashboard_env, repo) -> Spy:  # noqa: F811
    spy = Spy()

    async def exchange_code(self, code):
        if spy.exchange_error:
            raise spy.exchange_error
        return {}

    async def get_me(self):
        return spy.user

    def save_token_to_db(self, user_id, token_data=None):
        spy.saved.append(user_id)
        repo.merge(
            OAuthToken(
                user_id=user_id,
                client_credential_id=dashboard_env.credential_id,
                access_token="access-" + user_id,
                refresh_token="refresh",
                scope=["identify", "guilds"],
                expires_at=nowtz() + timedelta(days=7),
            )
        )

    async def revoke_token(self, token, token_type_hint="access_token"):
        if spy.revoke_error:
            raise spy.revoke_error
        spy.revoked.append(token)

    monkeypatch.setattr(DiscordOAuth, "exchange_code", exchange_code)
    monkeypatch.setattr(DiscordOAuth, "get_me", get_me)
    monkeypatch.setattr(DiscordOAuth, "save_token_to_db", save_token_to_db)
    monkeypatch.setattr(DiscordOAuth, "revoke_token", revoke_token)
    return spy


class Body(BaseModel):
    value: int


def make_app() -> FastAPI:
    """只有後台的 app：模擬 bot_website 的順序，先有 sentry 風格的 middleware 再 install。"""
    app = FastAPI()

    @app.middleware("http")
    async def boom_catcher(request: Request, call_next):
        try:
            return await call_next(request)
        except RuntimeError:
            return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})

    dashboard.install(app)

    extra = APIRouter(prefix="/dashboard")

    @extra.get("/boom")
    async def boom():
        raise RuntimeError("boom")

    @extra.put("/echo")
    async def echo(body: Body):
        return {"value": body.value}

    @extra.post("/nobody")
    async def nobody():
        return {"ok": True}

    app.include_router(extra)

    @app.get("/oauth/discord")
    async def oauth_discord(request: Request):
        # bot_website 的簡化版：後台分流，回 None 就 404
        return await auth.handle_dashboard_oauth(request) or JSONResponse(status_code=404, content={})

    @app.put("/other")
    async def other(body: Body):
        return {"value": body.value}

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(make_app(), base_url="https://testserver", follow_redirects=False)


def encode_cookie(state=STATE, purpose="login", next="/dashboard/guilds/1", origin=FRONTEND) -> str:
    raw = json.dumps({"state": state, "purpose": purpose, "next": next, "origin": origin})
    return base64.urlsafe_b64encode(raw.encode()).decode()


def login(client: TestClient, spy: Spy, **cookie):
    client.cookies.set("dashboard_oauth", encode_cookie(**cookie))
    return client.get("/oauth/discord", params={"code": "c", "state": STATE})


def make_session(repo, user_id=USER_ID, last_used_ago=timedelta(0), session_id="sid") -> str:  # noqa: F811
    repo.add(
        DashboardSession(
            session_id=session_id,
            discord_user_id=user_id,
            name="Some One",
            avatar=None,
            last_used_at=nowtz() - last_used_ago,
        )
    )
    return session_id


def set_cookies(response) -> list[str]:
    return response.headers.get_list("set-cookie")


# ====== 設定 ======
class TestSettings:
    BASE = dict(
        BOT_CODE="x", DB_HOST="h", DB_PORT=1, DB_USER="u", DB_PASSWORD="p", DB_NAME="n", ZEROTIER_NETWORK_ID="z",
        TASK_REPORT=1, FEEDBACK_CHANNEL=1, ERROR_REPORT=1, REPORT_CHANNEL=1, DM_CHANNEL=1, MENTIONED_CHANNEL=1,
        MENTION_EVERYONE_CHANNEL=1, VIP_ADMIN_CHANNEL=1, AUTH_SERVICE_KEY="k",
    )  # fmt: skip

    def test_not_required_without_website(self):
        AppSettings(**self.BASE, API_WEBSITE=False, _env_file=None)

    def test_required_with_website(self):
        with pytest.raises(ValueError, match="DASHBOARD_FRONTEND_URL"):
            AppSettings(**self.BASE, API_WEBSITE=True, _env_file=None)

    def test_ok_with_website(self):
        s = AppSettings(
            **self.BASE,
            API_WEBSITE=True,
            DASHBOARD_FRONTEND_URL=FRONTEND,
            DASHBOARD_ALLOWED_ORIGINS=ORIGINS,
            _env_file=None,
        )
        assert s.DASHBOARD_ALLOWED_ORIGINS == ORIGINS


# ====== DiscordUser、頭像 ======
class TestDiscordUser:
    def test_minimal_payload(self):
        user = DiscordUser(**{"id": "1", "username": "u", "avatar": None, "global_name": None, "banner": None})
        assert user.avatar is None and user.global_name is None and user.discriminator is None

    def test_only_required(self):
        DiscordUser(id="1", username="u")

    def test_avatar_url(self):
        assert auth.avatar_url("5", "hash").endswith("/avatars/5/hash.png")
        assert auth.avatar_url("5", "a_hash").endswith(".gif")
        assert auth.avatar_url(str(3 << 22), None) == "https://cdn.discordapp.com/embed/avatars/3.png"


# ====== next / origin ======
class TestSanitize:
    @pytest.mark.parametrize("value", ["/dashboard", "/dashboard/guilds/123", "/dashboard?x=1"])
    def test_next_ok(self, value):
        assert auth.sanitize_next(value) == value

    @pytest.mark.parametrize(
        "value",
        [
            None,
            "",
            "/",
            "//evil.com",
            "https://evil.com",
            "/dashboardx",
            "/dash",
            "/dashboard\\evil",
            "/dashboard/\r\nx",
            "dashboard",
        ],
    )
    def test_next_rejected(self, value):
        assert auth.sanitize_next(value) == "/dashboard"

    def test_origin(self):
        assert auth.sanitize_origin("https://www.domalyze.net") == "https://www.domalyze.net"
        assert auth.sanitize_origin("https://evil.example") == FRONTEND
        assert auth.sanitize_origin(None) == FRONTEND


# ====== 錯誤格式、CSRF、CORS ======
class TestErrorFormat:
    def test_validation_error_in_dashboard(self, client):
        r = client.put("/dashboard/echo", json={"value": "x"}, headers={"Origin": FRONTEND})
        assert r.status_code == 400
        assert r.json() == {"error": "invalid_request"}

    def test_validation_error_elsewhere_keeps_default(self, client):
        r = client.put("/other", json={"value": "x"})
        assert r.status_code == 422
        assert "detail" in r.json()

    def test_dashboard_error(self):
        app = FastAPI()
        dashboard.install(app)

        @app.get("/x")
        async def x():
            raise dashboard.errors.DashboardError(409, "conflict", deleted=True)

        r = TestClient(app).get("/x")
        assert r.status_code == 409
        assert r.json() == {"error": "conflict", "deleted": True}


class TestCsrf:
    def test_bad_origin(self, client):
        r = client.put("/dashboard/echo", json={"value": 1}, headers={"Origin": "https://memory.domalyze.net"})
        assert r.status_code == 400 and r.json() == {"error": "invalid_request"}

    def test_missing_origin(self, client):
        r = client.put("/dashboard/echo", json={"value": 1})
        assert r.status_code == 400

    def test_good_origin(self, client):
        r = client.put("/dashboard/echo", json={"value": 1}, headers={"Origin": "https://www.domalyze.net"})
        assert r.status_code == 200

    def test_body_must_be_json(self, client):
        r = client.put("/dashboard/echo", content="value=1", headers={"Origin": FRONTEND, "Content-Type": "text/plain"})
        assert r.status_code == 400 and r.json() == {"error": "invalid_request"}

    def test_no_body_needs_no_content_type(self, client):
        r = client.post("/dashboard/nobody", headers={"Origin": FRONTEND})
        assert r.status_code == 200

    def test_get_needs_no_origin(self, client):
        assert client.get("/dashboard/boom").status_code != 400

    def test_non_dashboard_path_unaffected(self, client):
        assert client.put("/other", json={"value": 1}).status_code == 200


class TestCors:
    def test_preflight(self, client):
        r = client.options(
            "/dashboard/echo",
            headers={
                "Origin": FRONTEND,
                "Access-Control-Request-Method": "PUT",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert r.status_code == 200
        assert r.headers["access-control-allow-origin"] == FRONTEND
        assert r.headers["access-control-allow-credentials"] == "true"
        assert "PUT" in r.headers["access-control-allow-methods"]
        assert "content-type" in r.headers["access-control-allow-headers"].lower()

    def test_disallowed_origin_gets_no_header(self, client):
        r = client.options(
            "/dashboard/echo", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "PUT"}
        )
        assert "access-control-allow-origin" not in r.headers

    def test_500_carries_cors_header(self, client):
        r = client.get("/dashboard/boom", headers={"Origin": FRONTEND})
        assert r.status_code == 500
        assert r.headers["access-control-allow-origin"] == FRONTEND


# ====== run_db / release_session ======
class TestRunDb:
    def test_releases_session_after_success_and_error(self, monkeypatch):
        calls = []
        monkeypatch.setattr(db, "sqldb", SimpleNamespace(release_session=lambda: calls.append(1)))

        def fail():
            raise ValueError("x")

        assert asyncio.run(db.run_db(lambda: 42)) == 42
        with pytest.raises(ValueError):
            asyncio.run(db.run_db(fail))
        assert len(calls) == 2

    def test_executor_is_small(self):
        assert db._executor._max_workers <= 4

    def test_release_session_noop_for_plain_session(self, repo):  # noqa: F811
        repo.release_session()  # 固定單一 Session 時不能把測試的 session 關掉
        assert repo.session.is_active

    def test_release_session_removes_scoped(self):
        removed = []

        from sqlalchemy.orm.scoping import ScopedSession

        scoped = ScopedSession.__new__(ScopedSession)
        scoped.remove = lambda: removed.append(1)  # pyright: ignore[reportAttributeAccessIssue]
        SQLRepository(real_sqldb.engine, scoped).release_session()
        assert removed == [1]


# ====== 登入入口 ======
class TestLoginEntry:
    def test_redirects_to_discord_with_scopes_and_cookie(self, client):
        r = client.get(
            "/to/dashboard-login", params={"next": "/dashboard/guilds/9", "origin": "https://www.domalyze.net"}
        )
        assert r.status_code == 307
        location = r.headers["location"]
        assert location.startswith("https://discord.com/api/oauth2/authorize")
        assert "scope=identify+guilds" in location or "scope=identify%20guilds" in location
        cookie = next(c for c in set_cookies(r) if c.startswith("dashboard_oauth="))
        assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie and "Max-Age=600" in cookie
        payload = json.loads(base64.urlsafe_b64decode(client.cookies["dashboard_oauth"]))
        assert payload["purpose"] == "login"
        assert payload["next"] == "/dashboard/guilds/9"
        assert payload["origin"] == "https://www.domalyze.net"
        assert f"state={payload['state']}" in location

    def test_bad_next_and_origin_use_defaults(self, client):
        client.get("/to/dashboard-login", params={"next": "//evil.com", "origin": "https://evil.example"})
        payload = json.loads(base64.urlsafe_b64decode(client.cookies["dashboard_oauth"]))
        assert payload["next"] == "/dashboard"
        assert payload["origin"] == FRONTEND

    def test_missing_params_use_defaults(self, client):
        client.get("/to/dashboard-login")
        payload = json.loads(base64.urlsafe_b64decode(client.cookies["dashboard_oauth"]))
        assert (payload["next"], payload["origin"]) == ("/dashboard", FRONTEND)


# ====== 登入 callback ======
class TestLoginCallback:
    def test_login_creates_session_and_redirects(self, client, spy, repo):  # noqa: F811
        r = login(client, spy, next="/dashboard/guilds/1", origin="https://www.domalyze.net")

        assert r.status_code == 307
        assert r.headers["location"] == "https://www.domalyze.net/dashboard/guilds/1"
        cookies = set_cookies(r)
        sess = next(c for c in cookies if c.startswith("dashboard_session="))
        assert "HttpOnly" in sess and "Secure" in sess and "SameSite=lax" in sess and f"Max-Age={30 * 86400}" in sess
        assert any(c.startswith("dashboard_oauth=") and "Max-Age=0" in c for c in cookies)
        row = repo.session.exec(select(DashboardSession)).one()
        assert (row.discord_user_id, row.name, row.avatar) == (USER_ID, "Some One", "abc")
        assert spy.saved == [USER_ID]

    def test_name_falls_back_to_username_and_default_avatar(self, client, spy, repo):  # noqa: F811
        spy.user = DiscordUser(id=USER_ID, username="plain", global_name=None, avatar=None)
        login(client, spy)
        me = client.get("/dashboard/me")
        assert me.status_code == 200
        assert me.json()["name"] == "plain"
        assert me.json()["avatar_url"].startswith("https://cdn.discordapp.com/embed/avatars/")

    def test_cancel_goes_to_origin_home(self, client, spy, repo):  # noqa: F811
        client.cookies.set("dashboard_oauth", encode_cookie(origin="https://www.domalyze.net"))
        r = client.get("/oauth/discord", params={"error": "access_denied", "state": STATE})
        assert r.headers["location"] == "https://www.domalyze.net/"
        assert not repo.session.exec(select(DashboardSession)).all()

    def test_tampered_cookie_is_revalidated(self, client, spy):
        r = login(client, spy, next="//evil.com", origin="https://evil.example")
        assert r.headers["location"] == f"{FRONTEND}/dashboard"

    def test_state_mismatch_returns_none(self, spy):
        request = SimpleNamespace(
            cookies={"dashboard_oauth": encode_cookie(state="other")}, query_params={"code": "c", "state": STATE}
        )
        assert asyncio.run(auth.handle_dashboard_oauth(request)) is None  # pyright: ignore[reportArgumentType]

    def test_exchange_failure_does_not_create_session(self, client, spy, repo):  # noqa: F811
        spy.exchange_error = Exception("bad code")
        r = login(client, spy)
        assert r.status_code == 400
        assert not repo.session.exec(select(DashboardSession)).all()

    def test_switching_account_deletes_old_session(self, client, spy, repo):  # noqa: F811
        make_session(repo, user_id=OTHER_ID, session_id="old")
        client.cookies.set("dashboard_session", "old")
        login(client, spy)
        ids = {row.discord_user_id for row in repo.session.exec(select(DashboardSession)).all()}
        assert ids == {USER_ID}


# ====== session ======
class TestSession:
    def test_me(self, client, repo):  # noqa: F811
        make_session(repo)
        client.cookies.set("dashboard_session", "sid")
        r = client.get("/dashboard/me")
        assert r.status_code == 200
        assert r.json()["id"] == USER_ID and r.json()["name"] == "Some One"

    def test_no_cookie(self, client):
        r = client.get("/dashboard/me")
        assert r.status_code == 401 and r.json() == {"error": "session_expired"}

    def test_unknown_session(self, client):
        client.cookies.set("dashboard_session", "nope")
        r = client.get("/dashboard/me")
        assert r.status_code == 401 and r.json() == {"error": "session_expired"}
        assert any(c.startswith("dashboard_session=") and "Max-Age=0" in c for c in set_cookies(r))

    def test_sliding_renewal(self, client, repo):  # noqa: F811
        make_session(repo, last_used_ago=timedelta(days=29))
        client.cookies.set("dashboard_session", "sid")
        r = client.get("/dashboard/me")
        assert r.status_code == 200
        assert any(c.startswith("dashboard_session=sid") and f"Max-Age={30 * 86400}" in c for c in set_cookies(r))
        repo.session.expire_all()
        row = repo.session.get(DashboardSession, "sid", populate_existing=True)
        assert nowtz() - row.last_used_at < timedelta(minutes=1)
        # 再過 29 天沒到期的話，因為上次使用已經重算，所以仍有效
        row.last_used_at = nowtz() - timedelta(days=29)
        repo.session.commit()
        assert client.get("/dashboard/me").status_code == 200

    def test_expired_after_30_days(self, client, repo):  # noqa: F811
        make_session(repo, last_used_ago=timedelta(days=30, minutes=1))
        client.cookies.set("dashboard_session", "sid")
        r = client.get("/dashboard/me")
        assert r.status_code == 401 and r.json() == {"error": "session_expired"}
        assert repo.session.get(DashboardSession, "sid", populate_existing=True) is None

    def test_cookie_survives_exception_response(self, repo):  # noqa: F811
        """端點拋例外時，續期的 Set-Cookie 仍然要在回應上。"""
        app = FastAPI()
        dashboard.install(app)
        r2 = APIRouter(prefix="/dashboard")

        @r2.get("/fail")
        async def fail(info=Depends(session.require_session)):
            raise dashboard.errors.DashboardError(403, "no_permission")

        app.include_router(r2)
        make_session(repo)
        c = TestClient(app, base_url="https://testserver")
        c.cookies.set("dashboard_session", "sid")
        r = c.get("/dashboard/fail")
        assert r.status_code == 403
        assert any(x.startswith("dashboard_session=sid") for x in set_cookies(r))


# ====== 登出 ======
class TestLogout:
    def _token(self, repo, dashboard_env, user_id=USER_ID):  # noqa: F811
        repo.merge(
            OAuthToken(
                user_id=user_id,
                client_credential_id=dashboard_env.credential_id,
                access_token="tok-" + user_id,
                refresh_token="r",
                scope=["identify", "guilds"],
                expires_at=nowtz() + timedelta(days=1),
            )
        )

    def test_logout_revokes_and_invalidates_all_devices(self, client, spy, repo, dashboard_env):  # noqa: F811
        make_session(repo, session_id="a")
        make_session(repo, session_id="b")
        make_session(repo, user_id=OTHER_ID, session_id="other")
        self._token(repo, dashboard_env)
        client.cookies.set("dashboard_session", "a")

        r = client.post("/dashboard/logout", headers={"Origin": FRONTEND})

        assert r.status_code == 200
        assert spy.revoked == ["tok-" + USER_ID]
        assert any(c.startswith("dashboard_session=") and "Max-Age=0" in c for c in set_cookies(r))
        assert not any("Max-Age=2592000" in c for c in set_cookies(r))
        repo.session.expire_all()
        assert repo.session.get(DashboardSession, "b", populate_existing=True) is None
        assert repo.session.get(DashboardSession, "other", populate_existing=True) is not None
        assert repo.get_oauth_token(USER_ID, dashboard_env.credential_id) is None
        client.cookies.set("dashboard_session", "b")
        assert client.get("/dashboard/me").status_code == 401

    def test_revoke_failure_still_logs_out(self, client, spy, repo, dashboard_env):  # noqa: F811
        make_session(repo)
        self._token(repo, dashboard_env)
        spy.revoke_error = Exception("discord down")
        client.cookies.set("dashboard_session", "sid")

        r = client.post("/dashboard/logout", headers={"Origin": FRONTEND})

        assert r.status_code == 200
        repo.session.expire_all()
        assert repo.session.get(DashboardSession, "sid", populate_existing=True) is None
        assert repo.get_oauth_token(USER_ID, dashboard_env.credential_id) is None

    def test_logout_requires_origin(self, client, repo):  # noqa: F811
        make_session(repo)
        client.cookies.set("dashboard_session", "sid")
        assert client.post("/dashboard/logout").status_code == 400

    def test_logout_without_session(self, client):
        r = client.post("/dashboard/logout", headers={"Origin": FRONTEND})
        assert r.status_code == 401 and r.json() == {"error": "session_expired"}


# ====== revoke ======
class TestRevokeToken:
    def test_posts_to_discord_revoke_endpoint(self):
        seen = {}

        class Resp:
            def raise_for_status(self):
                seen["checked"] = True

        class FakeClient:
            async def revoke_token(self, url, token, token_type_hint):
                seen.update(url=url, token=token, hint=token_type_hint)
                return Resp()

        oauth = DiscordOAuth(client_id="c", client_secret="s", redirect_uri="r")
        oauth._client = FakeClient()  # pyright: ignore[reportAttributeAccessIssue]
        asyncio.run(oauth.revoke_token("tok"))
        assert seen == {
            "url": "https://discord.com/api/oauth2/token/revoke",
            "token": "tok",
            "hint": "access_token",
            "checked": True,
        }


# ====== 自動掃描 ======
class TestAutoDiscovery:
    def test_scans_router_and_to_router_in_new_modules(self, tmp_path, monkeypatch):
        import sys
        import types

        module = types.ModuleType("starServer.dashboard.fake_card")
        module.router = APIRouter(prefix="/dashboard")
        module.to_router = APIRouter()

        @module.router.get("/fake")
        async def fake():
            return {"ok": 1}

        @module.to_router.get("/to/fake")
        async def to_fake():
            return {"ok": 2}

        monkeypatch.setitem(sys.modules, "starServer.dashboard.fake_card", module)
        monkeypatch.setattr(
            dashboard.pkgutil,
            "iter_modules",
            lambda path: [
                SimpleNamespace(name="fake_card"),
                SimpleNamespace(name="errors"),
                SimpleNamespace(name="_private"),
            ],
        )
        app = FastAPI()
        dashboard.install(app)
        c = TestClient(app)
        assert c.get("/dashboard/fake").json() == {"ok": 1}
        assert c.get("/to/fake").json() == {"ok": 2}


# ====== bot_website 整合 ======
@pytest.fixture
def site() -> TestClient:
    return TestClient(bot_website.app, base_url="https://testserver", follow_redirects=False)


class TestBotWebsite:
    def test_to_discordauth_removed(self, site):
        assert site.get("/to/discordauth").status_code == 404

    def test_dashboard_routes_mounted(self, site):
        assert site.get("/dashboard/me").json() == {"error": "session_expired"}
        assert site.get("/to/dashboard-login").status_code == 307

    def test_login_through_real_app(self, site, spy, repo):  # noqa: F811
        site.cookies.set("dashboard_oauth", encode_cookie())
        r = site.get("/oauth/discord", params={"code": "c", "state": STATE})
        assert r.headers["location"] == f"{FRONTEND}/dashboard/guilds/1"
        assert repo.session.exec(select(DashboardSession)).one().discord_user_id == USER_ID

    def test_state_mismatch_falls_back_and_clears_cookie(self, site, spy):
        site.cookies.set("dashboard_oauth", encode_cookie(state="other"))
        r = site.get("/oauth/discord", params={"code": "c", "state": STATE})
        assert r.headers["location"] == f"{FRONTEND}/dashboard"
        assert any(c.startswith("dashboard_oauth=") and "Max-Age=0" in c for c in set_cookies(r))
        assert spy.saved == []

    def test_state_mismatch_with_guild_id_is_bot_flow(self, site, spy):
        site.cookies.set("dashboard_oauth", encode_cookie(state="other"))
        r = site.get("/oauth/discord", params={"code": "c", "state": STATE, "guild_id": "1"})
        assert r.status_code == 200
        assert spy.saved == []

    def test_bot_flow_does_not_touch_token(self, site, spy, monkeypatch):
        async def must_not_call(self, code):
            raise AssertionError("bot 授權不該換 token")

        monkeypatch.setattr(DiscordOAuth, "exchange_code", must_not_call)
        r = site.get("/oauth/discord", params={"code": "c", "guild_id": "1", "permissions": "8"})
        assert r.status_code == 200
        assert "授權已完成" in r.text
        assert spy.saved == []

    def test_bot_flow_without_code(self, site):
        r = site.get("/oauth/discord", params={"guild_id": "1", "error": "access_denied"})
        assert r.status_code == 400

    def test_cancel_without_cookie_goes_to_frontend_home(self, site):
        r = site.get("/oauth/discord", params={"error": "access_denied"})
        assert r.headers["location"] == f"{FRONTEND}/"

    def test_no_cookie_no_guild_goes_to_dashboard(self, site):
        r = site.get("/oauth/discord", params={"code": "c"})
        assert r.status_code == 307 and r.headers["location"] == f"{FRONTEND}/dashboard"

    def test_other_routes_keep_working(self, site):
        assert site.get("/keep_alive").status_code == 200
        r = site.get("/to/discordbot")
        assert r.status_code == 307 and "oauth_state=" in r.headers["set-cookie"]
