"""伺服器管理後台測試共用：假 OAuth 與 session、測試用 FastAPI app，以及 `dashboard_env`、`spy`、`site` fixture。"""

from __future__ import annotations

import base64
import json
from datetime import timedelta

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
from starlib.oauth import DiscordOAuth
from starlib.oauth.models import DiscordUser
from starlib.utils import nowtz
from starServer import bot_website, dashboard
from starServer.dashboard import auth, channel_mods, db, session
from tests.helpers.dashboard_setup import (  # noqa: F401  其他測試檔從這裡 import
    BOT_TWITCH_ID,
    USER_ID,
    FakeModerators,
    install_fakes,
    make_domalyze_session,
    make_session,
    make_twitch_session,
)

FRONTEND = "https://domalyze.net"
ORIGINS = ["https://domalyze.net", "https://www.domalyze.net"]
STATE = "state-abc"


@pytest.fixture
def dashboard_env(monkeypatch, repo):
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
    monkeypatch.setattr(channel_mods, "sqldb", repo)
    return install_fakes(
        monkeypatch.setattr,
        frontend_url=FRONTEND,
        allowed_origins=ORIGINS,
        credential_id=credential_id,
    )


@pytest.fixture
def twitch_mods(dashboard_env) -> FakeModerators:
    return dashboard_env.moderators


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


def set_cookies(response) -> list[str]:
    return response.headers.get_list("set-cookie")


@pytest.fixture
def site() -> TestClient:
    return TestClient(bot_website.app, base_url="https://testserver", follow_redirects=False)
