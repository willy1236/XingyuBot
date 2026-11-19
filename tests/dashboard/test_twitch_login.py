"""Twitch 登入（W-01）：/to/dashboard-twitch-login 與 /oauth/twitch 的後台分流（假 Twitch，真實 PostgreSQL，交易結束後 rollback）。"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient
from sqlmodel import select

from starlib.database import DashboardSession, TwitchBotJoinChannel
from starlib.oauth import TwitchOAuth
from starlib.providers.social.models import TwitchUser
from starServer.dashboard import twitch_login
from tests.helpers.dashboard_auth import FRONTEND, STATE, make_session, set_cookies, site  # noqa: F401  (fixture)

pytestmark = pytest.mark.usefixtures("dashboard_env")

TWITCH_ID = 2000000001
COOKIE = "dashboard_twitch_oauth"


class Spy:
    def __init__(self):
        self.exchange_error: Exception | None = None
        self.get_me_error: Exception | None = None
        self.saved_tokens: list[str] = []
        self.scopes: list[list[str] | None] = []


def _twitch_user(login="streamer", name="Streamer") -> TwitchUser:
    return TwitchUser(
        id=str(TWITCH_ID),
        login=login,
        display_name=name,
        type="",
        broadcaster_type="",
        description="",
        profile_image_url="https://example.invalid/p.png",
        view_count=0,
        created_at=datetime(2020, 1, 1, tzinfo=UTC),
    )


@pytest.fixture
def spy(monkeypatch, repo) -> Spy:
    spy = Spy()
    monkeypatch.setattr(twitch_login, "sqldb", repo)
    monkeypatch.setattr(
        twitch_login,
        "_oauth_client_cache",
        SimpleNamespace(
            client_id="cid",
            client_secret="secret",
            redirect_uri="https://api.example.test/oauth/twitch",
            default_scopes=["chat:read", "moderation:read"],
            credential_id=1,
        ),
    )

    async def exchange_code(self, code):
        spy.scopes.append(self.scopes)
        if spy.exchange_error:
            raise spy.exchange_error
        return {}

    async def get_me(self):
        if spy.get_me_error:
            raise spy.get_me_error
        return _twitch_user()

    def save_token_to_db(self, user_id, token_data=None):
        spy.saved_tokens.append(user_id)

    monkeypatch.setattr(TwitchOAuth, "exchange_code", exchange_code)
    monkeypatch.setattr(TwitchOAuth, "get_me", get_me)
    monkeypatch.setattr(TwitchOAuth, "save_token_to_db", save_token_to_db)
    return spy


def _cookie(state=STATE, purpose="login", next="/dashboard", origin=FRONTEND) -> str:
    raw = json.dumps({"state": state, "purpose": purpose, "next": next, "origin": origin})
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _callback(site: TestClient, *, cookie: str | None = None, **params):
    site.cookies.set(COOKIE, cookie if cookie is not None else _cookie())
    params.setdefault("state", STATE)
    return site.get("/oauth/twitch", params=params)


def _channel(repo) -> TwitchBotJoinChannel | None:
    return repo.session.get(TwitchBotJoinChannel, TWITCH_ID, populate_existing=True)


def _sessions(repo) -> list[DashboardSession]:
    return list(repo.session.exec(select(DashboardSession)).all())


def _cookie_deleted(response, name=COOKIE) -> bool:
    return any(h.startswith(f"{name}=") and "Max-Age=0" in h for h in set_cookies(response))


@pytest.fixture(autouse=True)
def _no_channel(repo):
    # 本機 DB 可能留有手動測試登記的頻道列；在外層交易內清掉，測完隨 rollback 還原
    existing = _channel(repo)
    if existing is not None:
        repo.session.delete(existing)
        repo.session.flush()


class TestLoginEntry:
    def test_redirects_to_twitch_without_scope(self, site, spy):
        response = site.get("/to/dashboard-twitch-login", params={"next": "/dashboard/channels/5", "origin": FRONTEND})

        assert response.status_code == 307
        location = urlparse(response.headers["location"])
        assert f"{location.scheme}://{location.netloc}{location.path}" == "https://id.twitch.tv/oauth2/authorize"
        query = parse_qs(location.query)
        assert "scope" not in query
        assert query["client_id"] == ["cid"]

    def test_cookie_carries_state_and_sanitized_next(self, site, spy):
        response = site.get(
            "/to/dashboard-twitch-login", params={"next": "https://evil.example", "origin": "https://evil.example"}
        )

        state = parse_qs(urlparse(response.headers["location"]).query)["state"][0]
        header = next(h for h in set_cookies(response) if h.startswith(f"{COOKIE}="))
        cookie = json.loads(base64.urlsafe_b64decode(header.split(";")[0].split("=", 1)[1]))
        assert cookie == {"state": state, "purpose": "login", "next": "/dashboard", "origin": FRONTEND}
        assert "HttpOnly" in header and "Secure" in header and "Max-Age=600" in header


class TestLogin:
    def test_creates_twitch_session_and_inactive_channel(self, site, spy, repo):
        response = _callback(site, code="c")

        assert response.status_code == 307
        assert response.headers["location"] == f"{FRONTEND}/dashboard/channels/{TWITCH_ID}"
        (row,) = _sessions(repo)
        assert (row.login_method, row.discord_user_id, row.twitch_user_id) == ("twitch", None, str(TWITCH_ID))
        assert (row.twitch_login, row.twitch_name, row.account_id) == ("streamer", "Streamer", None)
        assert any(h.startswith("dashboard_session=") and row.session_id in h for h in set_cookies(response))
        channel = _channel(repo)
        assert channel is not None
        assert (channel.state, channel.login, channel.display_name) == ("inactive", "streamer", "Streamer")
        assert channel.avatar_url == "https://example.invalid/p.png"
        assert channel.first_seen_at is not None
        assert _cookie_deleted(response)

    def test_uses_empty_scope_and_never_saves_token(self, site, spy):
        _callback(site, code="c")

        assert spy.scopes == [[]]
        assert spy.saved_tokens == []

    def test_keeps_requested_next(self, site, spy):
        response = _callback(site, cookie=_cookie(next=f"/dashboard/channels/{TWITCH_ID}/commands"), code="c")

        assert response.headers["location"] == f"{FRONTEND}/dashboard/channels/{TWITCH_ID}/commands"

    def test_existing_channel_keeps_settings(self, site, spy, repo):
        repo.add(
            TwitchBotJoinChannel(
                twitch_id=TWITCH_ID,
                action_channel_id=99,
                point_name="pt",
                state="enabled",
                login="old",
                display_name="Old",
            )
        )

        _callback(site, code="c")

        channel = _channel(repo)
        assert (channel.state, channel.action_channel_id, channel.point_name) == ("enabled", 99, "pt")
        assert (channel.login, channel.display_name) == ("streamer", "Streamer")

    def test_replaces_session_in_cookie(self, site, spy, repo):
        old = make_session(repo)
        site.cookies.set("dashboard_session", old)

        _callback(site, code="c")

        sessions = _sessions(repo)
        assert [s.login_method for s in sessions] == ["twitch"]
        assert sessions[0].session_id != old

    def test_second_login_keeps_one_channel(self, site, spy, repo):
        _callback(site, code="c")
        _callback(site, code="c")

        rows = repo.session.exec(select(TwitchBotJoinChannel).where(TwitchBotJoinChannel.twitch_id == TWITCH_ID)).all()
        assert len(rows) == 1


class TestLoginFailed:
    @pytest.mark.parametrize("params", [{"error": "access_denied", "code": "c"}, {}])
    def test_denied_or_missing_code_returns_to_login_page(self, site, spy, repo, params):
        response = _callback(site, **params)

        assert response.headers["location"] == f"{FRONTEND}/dashboard-login"
        assert _sessions(repo) == []
        assert _channel(repo) is None
        assert not any(h.startswith("dashboard_session=") for h in set_cookies(response))
        assert _cookie_deleted(response)

    @pytest.mark.parametrize("where", ["exchange_error", "get_me_error"])
    def test_twitch_failure_returns_to_login_page(self, site, spy, repo, where):
        setattr(spy, where, RuntimeError("boom"))

        response = _callback(site, code="c")

        assert response.headers["location"] == f"{FRONTEND}/dashboard-login"
        assert _sessions(repo) == []
        assert _channel(repo) is None


class TestDispatch:
    def test_unknown_purpose_goes_to_dashboard(self, site, spy):
        response = _callback(site, cookie=_cookie(purpose="nope"), code="c")

        assert response.headers["location"] == f"{FRONTEND}/dashboard"
        assert _cookie_deleted(response)

    def test_registered_purpose_is_dispatched(self, site, spy, monkeypatch):
        calls = []

        async def handler(request, cookie):
            calls.append(cookie.purpose)
            return RedirectResponse(url=f"{cookie.origin}/x")

        monkeypatch.setitem(twitch_login._purpose_handlers, "enable", handler)

        response = _callback(site, cookie=_cookie(purpose="enable"), code="c")

        assert calls == ["enable"]
        assert response.headers["location"] == f"{FRONTEND}/x"

    def test_state_mismatch_falls_back_and_clears_cookie(self, site, spy, repo):
        response = _callback(site, state="other", code="c")

        assert response.status_code == 400
        assert _sessions(repo) == []
        assert _cookie_deleted(response)

    def test_without_cookie_uses_old_flow(self, site, spy):
        response = site.get("/oauth/twitch", params={"code": "c", "state": STATE})

        assert response.status_code == 400
        assert not _cookie_deleted(response)
