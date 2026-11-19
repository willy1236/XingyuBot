"""伺服器管理後台測試共用：假 OAuth 與 session、測試用 FastAPI app，以及 `dashboard_env`、`spy`、`site` fixture。"""

from __future__ import annotations

import base64
import json
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlmodel import delete

from starlib import sqldb as real_sqldb
from starlib import website_stats
from starlib.database import APIType, DashboardSession, OAuthToken, WebsiteLinkClick, WebsiteWeeklyActivity
from starlib.identity import resolver as resolver_module
from starlib.oauth import DiscordOAuth
from starlib.oauth.models import DiscordUser
from starlib.utils import nowtz
from starServer import bot_website, dashboard
from starServer.dashboard import auth, config, db, discord_users, session
from tests.helpers.identity import FakeDirectory

FRONTEND = "https://domalyze.net"
ORIGINS = ["https://domalyze.net", "https://www.domalyze.net"]
STATE = "state-abc"
USER_ID = "111111111111111111"


@pytest.fixture
def dashboard_env(monkeypatch, repo):
    monkeypatch.setattr(config, "frontend_url", lambda: FRONTEND)
    monkeypatch.setattr(config, "allowed_origins", lambda: ORIGINS)
    for module in (db, session, auth, website_stats):
        monkeypatch.setattr(module, "sqldb", repo)
    monkeypatch.setattr(website_stats, "_recorded", (website_stats.date.min, set()))
    # 本機 DB 可能有手動測試留下的 session 與統計；在外層交易內清掉，測完隨 rollback 還原
    for table in (DashboardSession, WebsiteWeeklyActivity, WebsiteLinkClick):
        repo.session.exec(delete(table))
    repo.session.flush()
    # 不讀真實的 oauth client，但 credential_id 要是真的（OAuthToken 有外鍵）
    credential_id = real_sqldb.get_oauth_client(APIType.Discord, 4).credential_id
    real_sqldb.release_session()
    fake_client = SimpleNamespace(
        client_id="cid",
        client_secret="secret",
        redirect_uri="https://api.example.test/oauth/discord",
        default_scopes=["identify"],
        credential_id=credential_id,
        # 假的 auth server：預設查無此人，各測試可設定 directory.accounts
        directory=FakeDirectory(),
    )
    monkeypatch.setattr(auth, "_oauth_client_cache", fake_client)
    monkeypatch.setattr(resolver_module, "_directory", fake_client.directory)
    monkeypatch.setattr(session, "_followed", {})
    monkeypatch.setattr(session, "_inflight", {})
    monkeypatch.setattr(session, "_unavailable_until", 0.0)
    monkeypatch.setattr(discord_users, "_fetched", {})
    return fake_client


class Spy:
    def __init__(self):
        self.revoked: list[str] = []
        self.user = DiscordUser(id=USER_ID, username="someone", global_name="Some One", avatar="abc")
        self.exchange_error: Exception | None = None
        self.saved: list[str] = []


@pytest.fixture
def spy(monkeypatch, dashboard_env, repo) -> Spy:
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


def make_session(repo, user_id=USER_ID, last_used_ago=timedelta(0), session_id="sid") -> str:
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


def make_domalyze_session(repo, account_id, user_id: str | None = USER_ID, session_id="dsid") -> str:
    """析域登入的 session；user_id 為 None 時是沒有 Discord 身分的析域 session。"""
    repo.add(
        DashboardSession(
            session_id=session_id,
            discord_user_id=user_id,
            name="willy",
            avatar=None,
            account_id=account_id,
            via_domalyze=True,
            login_method="domalyze",
        )
    )
    return session_id


def make_twitch_session(repo, twitch_id="777", session_id="tsid", login="streamer", name="Streamer") -> str:
    repo.add(
        DashboardSession(
            session_id=session_id,
            discord_user_id=None,
            name=name,
            avatar=f"https://static-cdn.jtvnw.net/{twitch_id}.png",
            login_method="twitch",
            twitch_user_id=twitch_id,
            twitch_login=login,
            twitch_name=name,
            twitch_avatar=f"https://static-cdn.jtvnw.net/{twitch_id}.png",
        )
    )
    return session_id


def set_cookies(response) -> list[str]:
    return response.headers.get_list("set-cookie")


@pytest.fixture
def site() -> TestClient:
    return TestClient(bot_website.app, base_url="https://testserver", follow_redirects=False)
