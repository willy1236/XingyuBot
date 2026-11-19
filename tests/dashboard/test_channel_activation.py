"""實況主啟用與停用 bot（W-03）：/to/dashboard-twitch-enable、enable handler 與 POST /dashboard/channels/{id}/disable（假 Twitch，真實 PostgreSQL，交易結束後 rollback）。"""

from __future__ import annotations

import base64
import json
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import func, select

from starlib.database import OAuthToken, TwitchBotJoinChannel, TwitchChatCommand
from starlib.identity.client import LinkedPassport, ResolvedAccount
from starlib.messaging.rpc import RpcHandlerError
from starlib.oauth import TwitchOAuth
from starlib.providers.social.models import TwitchUser
from starServer.dashboard import channel_activation, twitch_control, twitch_login
from tests.helpers.dashboard_auth import (
    FRONTEND,
    STATE,
    make_domalyze_session,
    make_session,
    make_twitch_session,
    set_cookies,
    site,  # noqa: F401  (fixture)
)
from tests.helpers.identity import _account

pytestmark = pytest.mark.usefixtures("dashboard_env")

TWITCH_ID = 2000000001
CHANNEL = str(TWITCH_ID)
BOT_ID = "999"
DISCORD_ID = "111111111111111111"
COOKIE = "dashboard_twitch_oauth"
CHANNEL_URL = f"{FRONTEND}/dashboard/twitch/{CHANNEL}"
LOGIN_URL = f"{FRONTEND}/dashboard-login?next=%2Fdashboard%2Ftwitch%2F{CHANNEL}"


class Spy:
    def __init__(self):
        self.exchange_error: Exception | None = None
        self.user_id = CHANNEL
        self.saved_tokens: list[str] = []
        self.scopes: list[list[str] | None] = []
        self.mod_status = 204
        self.mod_text = ""
        #: 400 時的後續查詢（GET moderators）：狀態碼與 data
        self.mod_list_status = 200
        self.mod_list_data: list[dict] = []
        self.mod_error: Exception | None = None
        self.mod_requests: list[httpx.Request] = []
        self.sync_result: object = twitch_control.SyncResult(joined=True)
        self.sync_calls: list[int] = []


def _twitch_user(user_id: str) -> TwitchUser:
    return TwitchUser(
        id=user_id,
        login="streamer",
        display_name="Streamer",
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
    for module in (twitch_login, channel_activation):
        monkeypatch.setattr(module, "sqldb", repo)
    monkeypatch.setattr(
        twitch_login,
        "_oauth_client_cache",
        SimpleNamespace(
            client_id="cid",
            client_secret="secret",
            redirect_uri="https://api.example.test/oauth/twitch",
            default_scopes=["chat:read"],
            credential_id=1,
        ),
    )
    monkeypatch.setattr(channel_activation, "_bot_user_id_cache", BOT_ID)

    async def exchange_code(self, code):
        spy.scopes.append(self.scopes)
        if spy.exchange_error:
            raise spy.exchange_error
        return {"access_token": "broadcaster-token"}

    async def get_me(self):
        return _twitch_user(spy.user_id)

    def save_token_to_db(self, user_id, token_data=None):
        spy.saved_tokens.append(user_id)

    monkeypatch.setattr(TwitchOAuth, "exchange_code", exchange_code)
    monkeypatch.setattr(TwitchOAuth, "get_me", get_me)
    monkeypatch.setattr(TwitchOAuth, "save_token_to_db", save_token_to_db)

    def handler(request: httpx.Request) -> httpx.Response:
        spy.mod_requests.append(request)
        if spy.mod_error:
            raise spy.mod_error
        if request.method == "GET":
            return httpx.Response(spy.mod_list_status, json={"data": spy.mod_list_data})
        return httpx.Response(spy.mod_status, text=spy.mod_text)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        channel_activation.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )

    async def sync_channel(twitch_id):
        spy.sync_calls.append(twitch_id)
        if isinstance(spy.sync_result, Exception):
            raise spy.sync_result
        return spy.sync_result

    monkeypatch.setattr(twitch_control, "sync_channel", sync_channel)
    return spy


@pytest.fixture(autouse=True)
def _no_channel(repo):
    # 本機 DB 可能留有手動測試登記的頻道列；在外層交易內清掉，測完隨 rollback 還原
    existing = repo.session.get(TwitchBotJoinChannel, TWITCH_ID)
    if existing is not None:
        repo.session.delete(existing)
        repo.session.flush()


def _cookie(state=STATE, channel_id: str | None = CHANNEL, origin=FRONTEND) -> str:
    raw = {"state": state, "purpose": "enable", "next": "/dashboard", "origin": origin}
    if channel_id is not None:
        raw["channel_id"] = channel_id
    return base64.urlsafe_b64encode(json.dumps(raw).encode()).decode()


def _own_channel_session(site, repo):
    site.cookies.set("dashboard_session", make_twitch_session(repo, twitch_id=CHANNEL))


def _callback(site: TestClient, *, cookie: str | None = None, **params):
    site.cookies.set(COOKIE, cookie if cookie is not None else _cookie())
    params.setdefault("state", STATE)
    return site.get("/oauth/twitch", params=params)


def _channel(repo) -> TwitchBotJoinChannel | None:
    return repo.session.get(TwitchBotJoinChannel, TWITCH_ID, populate_existing=True)


def _notices(response) -> list[str]:
    query = parse_qs(urlparse(response.headers["location"]).query)
    return query["notice"][0].split(",") if "notice" in query else []


class TestEntry:
    def _enter(self, site, **params):
        params.setdefault("channel", CHANNEL)
        params.setdefault("origin", FRONTEND)
        return site.get("/to/dashboard-twitch-enable", params=params)

    def test_redirects_to_twitch_with_full_scopes(self, site, spy, repo):
        _own_channel_session(site, repo)

        response = self._enter(site)

        assert response.status_code == 307
        location = urlparse(response.headers["location"])
        assert f"{location.scheme}://{location.netloc}{location.path}" == "https://id.twitch.tv/oauth2/authorize"
        query = parse_qs(location.query)
        assert query["scope"] == [" ".join(channel_activation.ENABLE_SCOPES)]
        assert query["force_verify"] == ["true"]

    def test_cookie_carries_purpose_and_channel(self, site, spy, repo):
        _own_channel_session(site, repo)

        response = self._enter(site)

        state = parse_qs(urlparse(response.headers["location"]).query)["state"][0]
        header = next(h for h in set_cookies(response) if h.startswith(f"{COOKIE}="))
        cookie = json.loads(base64.urlsafe_b64decode(header.split(";")[0].split("=", 1)[1]))
        assert cookie == {
            "state": state,
            "purpose": "enable",
            "next": "/dashboard",
            "origin": FRONTEND,
            "channel_id": CHANNEL,
        }

    def test_without_session_goes_to_login_page(self, site, spy):
        response = self._enter(site)

        assert response.headers["location"] == LOGIN_URL
        assert COOKIE not in "".join(set_cookies(response))

    def test_other_channel_goes_back_to_channel_page(self, site, spy, repo):
        site.cookies.set("dashboard_session", make_twitch_session(repo, twitch_id="777"))

        response = self._enter(site)

        assert response.headers["location"] == CHANNEL_URL
        assert COOKIE not in "".join(set_cookies(response))

    def test_discord_only_session_has_no_channel(self, site, spy, repo):
        site.cookies.set("dashboard_session", make_session(repo))

        response = self._enter(site)

        assert response.headers["location"] == CHANNEL_URL

    @pytest.mark.parametrize("channel", [None, "abc"])
    def test_bad_channel_goes_to_channel_list(self, site, spy, channel):
        params = {"origin": FRONTEND}
        if channel is not None:
            params["channel"] = channel
        response = site.get("/to/dashboard-twitch-enable", params=params)

        assert response.headers["location"] == f"{FRONTEND}/dashboard/twitch"

    def test_unknown_origin_falls_back_to_frontend(self, site, spy):
        response = self._enter(site, origin="https://evil.example")

        assert response.headers["location"].startswith(f"{FRONTEND}/dashboard-login")


class TestEnable:
    def test_enables_and_syncs(self, site, spy, repo):
        _own_channel_session(site, repo)

        response = _callback(site, code="c")

        assert response.headers["location"] == CHANNEL_URL
        assert spy.scopes == [channel_activation.ENABLE_SCOPES]
        assert spy.saved_tokens == [CHANNEL]
        channel = _channel(repo)
        assert (channel.state, channel.login, channel.display_name) == ("enabled", "streamer", "Streamer")
        assert spy.sync_calls == [TWITCH_ID]
        assert any(h.startswith(f"{COOKIE}=") and "Max-Age=0" in h for h in set_cookies(response))

    def test_adds_bot_as_mod_with_broadcaster_token(self, site, spy, repo):
        _own_channel_session(site, repo)

        _callback(site, code="c")

        (request,) = spy.mod_requests
        assert request.method == "POST"
        assert request.url.path == "/helix/moderation/moderators"
        assert dict(request.url.params) == {"broadcaster_id": CHANNEL, "user_id": BOT_ID}
        assert request.headers["authorization"] == "Bearer broadcaster-token"
        assert request.headers["client-id"] == "cid"

    def test_updates_existing_row_and_keeps_settings(self, site, spy, repo):
        repo.add(
            TwitchBotJoinChannel(
                twitch_id=TWITCH_ID, action_channel_id=99, point_name="pt", state="disabled", login="old"
            )
        )
        repo.add(TwitchChatCommand(twitch_id=TWITCH_ID, name="hi", response="hello"))
        _own_channel_session(site, repo)

        _callback(site, code="c")

        channel = _channel(repo)
        assert (channel.state, channel.action_channel_id, channel.point_name, channel.login) == (
            "enabled",
            99,
            "pt",
            "streamer",
        )
        assert repo.session.get(TwitchChatCommand, (TWITCH_ID, "hi")) is not None

    def test_bad_request_with_bot_already_mod_counts_as_success(self, site, spy, repo):
        # 不依賴 Twitch 400 的訊息內容：400 時查名單，bot 在名單裡就是已經是 mod
        spy.mod_status = 400
        spy.mod_text = "any text Twitch decides to send"
        spy.mod_list_data = [{"user_id": BOT_ID}]
        _own_channel_session(site, repo)

        response = _callback(site, code="c")

        assert response.headers["location"] == CHANNEL_URL
        post, get = spy.mod_requests
        assert get.method == "GET"
        assert get.url.path == "/helix/moderation/moderators"
        assert dict(get.url.params) == {"broadcaster_id": CHANNEL, "user_id": BOT_ID}
        assert get.headers["authorization"] == "Bearer broadcaster-token"

    @pytest.mark.parametrize(
        ("list_status", "list_data"), [(200, []), (401, []), (500, [])], ids=["not_in_list", "unauthorized", "error"]
    )
    def test_bad_request_without_bot_in_list_is_mod_failed(self, site, spy, repo, list_status, list_data):
        spy.mod_status = 400
        spy.mod_text = "The user specified in the user_id query parameter is already a moderator"
        spy.mod_list_status = list_status
        spy.mod_list_data = list_data
        _own_channel_session(site, repo)

        response = _callback(site, code="c")

        assert _notices(response) == ["mod_failed"]

    @pytest.mark.parametrize("status", [401, 403, 422, 429, 500])
    def test_mod_failure_still_enables(self, site, spy, repo, status):
        spy.mod_status = status
        _own_channel_session(site, repo)

        response = _callback(site, code="c")

        assert _notices(response) == ["mod_failed"]
        assert _channel(repo).state == "enabled"
        assert spy.sync_calls == [TWITCH_ID]

    def test_mod_network_error_still_enables(self, site, spy, repo):
        spy.mod_error = httpx.ConnectError("down")
        _own_channel_session(site, repo)

        response = _callback(site, code="c")

        assert _notices(response) == ["mod_failed"]
        assert _channel(repo).state == "enabled"

    def test_bot_offline_keeps_authorization(self, site, spy, repo):
        spy.sync_result = twitch_control.BotOffline()
        _own_channel_session(site, repo)

        response = _callback(site, code="c")

        assert _notices(response) == ["bot_offline"]
        assert spy.saved_tokens == [CHANNEL]
        assert _channel(repo).state == "enabled"

    def test_bot_internal_error_is_reported_as_offline(self, site, spy, repo):
        spy.sync_result = RpcHandlerError("boom")
        _own_channel_session(site, repo)

        response = _callback(site, code="c")

        assert _notices(response) == ["bot_offline"]
        assert _channel(repo).state == "enabled"

    def test_mod_failure_and_bot_offline_are_both_reported(self, site, spy, repo):
        spy.mod_status = 422
        spy.sync_result = twitch_control.BotOffline()
        _own_channel_session(site, repo)

        response = _callback(site, code="c")

        assert _notices(response) == ["mod_failed", "bot_offline"]

    def test_wrong_account_saves_nothing(self, site, spy, repo):
        spy.user_id = "123456"
        _own_channel_session(site, repo)

        response = _callback(site, code="c")

        assert _notices(response) == ["wrong_account"]
        assert response.headers["location"].startswith(CHANNEL_URL)
        assert spy.saved_tokens == []
        assert spy.mod_requests == []
        assert spy.sync_calls == []
        assert _channel(repo) is None

    @pytest.mark.parametrize("params", [{"error": "access_denied", "code": "c"}, {}])
    def test_cancel_returns_to_channel_page(self, site, spy, repo, params):
        _own_channel_session(site, repo)

        response = _callback(site, **params)

        assert response.headers["location"] == CHANNEL_URL
        assert spy.scopes == []
        assert _channel(repo) is None

    def test_exchange_failure_reports_enable_failed(self, site, spy, repo):
        spy.exchange_error = RuntimeError("boom")
        _own_channel_session(site, repo)

        response = _callback(site, code="c")

        assert _notices(response) == ["enable_failed"]
        assert spy.saved_tokens == []
        assert _channel(repo) is None

    def test_expired_session_goes_to_login_page(self, site, spy):
        response = _callback(site, code="c")

        assert response.headers["location"] == LOGIN_URL
        assert spy.saved_tokens == []

    def test_session_without_the_channel_saves_nothing(self, site, spy, repo):
        site.cookies.set("dashboard_session", make_twitch_session(repo, twitch_id="777"))

        response = _callback(site, code="c")

        assert response.headers["location"] == CHANNEL_URL
        assert spy.saved_tokens == []

    def test_cookie_without_channel_goes_to_channel_list(self, site, spy, repo):
        _own_channel_session(site, repo)

        response = _callback(site, cookie=_cookie(channel_id=None), code="c")

        assert response.headers["location"] == f"{FRONTEND}/dashboard/twitch"
        assert spy.saved_tokens == []


class TestDomalyzeSession:
    """析域登入的 session：頻道來自帳號連結的 Twitch，要經過帳號跟隨才有（lookup_session 只讀 session 列，沒有）。"""

    @pytest.fixture
    def linked(self, repo, dashboard_env):
        def make(passports=((CHANNEL, "Streamer"),), discord=True):
            account = replace(
                _account(twitch_passports=[LinkedPassport(subject, name) for subject, name in passports]),
                discord_passports=(LinkedPassport(DISCORD_ID, "willy"),),
            )
            dashboard_env.directory.by_account_id[account.account_id] = ResolvedAccount(account)
            return make_domalyze_session(repo, account.account_id, user_id=DISCORD_ID if discord else None)

        return make

    @pytest.mark.parametrize("discord", [True, False], ids=["with_discord", "without_discord"])
    def test_entry_redirects_to_twitch(self, site, spy, linked, discord):
        site.cookies.set("dashboard_session", linked(discord=discord))

        response = site.get("/to/dashboard-twitch-enable", params={"channel": CHANNEL, "origin": FRONTEND})

        assert response.headers["location"].startswith("https://id.twitch.tv/oauth2/authorize")
        assert any(h.startswith(f"{COOKIE}=") for h in set_cookies(response))

    def test_entry_for_unlinked_channel_goes_back_to_channel_page(self, site, spy, linked):
        site.cookies.set("dashboard_session", linked(passports=(("777", "Other"),)))

        response = site.get("/to/dashboard-twitch-enable", params={"channel": CHANNEL, "origin": FRONTEND})

        assert response.headers["location"] == CHANNEL_URL

    @pytest.mark.parametrize("discord", [True, False], ids=["with_discord", "without_discord"])
    def test_callback_enables(self, site, spy, repo, linked, discord):
        site.cookies.set("dashboard_session", linked(discord=discord))

        response = _callback(site, code="c")

        assert response.headers["location"] == CHANNEL_URL
        assert spy.saved_tokens == [CHANNEL]
        assert _channel(repo).state == "enabled"

    def test_revoked_account_goes_to_login_page(self, site, spy, linked, dashboard_env):
        # 帳號停權或查無：session 失效，導向登入頁而不是靜默回頻道頁
        site.cookies.set("dashboard_session", linked())
        dashboard_env.directory.by_account_id.clear()

        response = site.get("/to/dashboard-twitch-enable", params={"channel": CHANNEL, "origin": FRONTEND})

        assert response.headers["location"] == LOGIN_URL


class TestDisable:
    def _disable(self, site):
        return site.post(f"/dashboard/channels/{CHANNEL}/disable", headers={"Origin": FRONTEND})

    def test_disables_and_syncs(self, site, spy, repo):
        repo.add(TwitchBotJoinChannel(twitch_id=TWITCH_ID, state="enabled"))
        _own_channel_session(site, repo)

        response = self._disable(site)

        assert response.status_code == 200
        assert response.json() == {"state": "disabled", "bot_offline": False}
        assert _channel(repo).state == "disabled"
        assert spy.sync_calls == [TWITCH_ID]

    def test_keeps_settings_and_token(self, site, spy, repo):
        repo.add(TwitchBotJoinChannel(twitch_id=TWITCH_ID, state="enabled", action_channel_id=99, point_name="pt"))
        repo.add(TwitchChatCommand(twitch_id=TWITCH_ID, name="hi", response="hello"))
        count = select(func.count()).select_from(OAuthToken)
        before = repo.session.exec(count).one()
        _own_channel_session(site, repo)

        self._disable(site)

        channel = _channel(repo)
        assert (channel.action_channel_id, channel.point_name) == (99, "pt")
        assert repo.session.get(TwitchChatCommand, (TWITCH_ID, "hi")) is not None
        assert repo.session.exec(count).one() == before

    def test_reenable_restores_state(self, site, spy, repo):
        repo.add(TwitchBotJoinChannel(twitch_id=TWITCH_ID, state="enabled", action_channel_id=99))
        _own_channel_session(site, repo)
        self._disable(site)

        _callback(site, code="c")

        channel = _channel(repo)
        assert (channel.state, channel.action_channel_id) == ("enabled", 99)

    def test_bot_offline_still_disables(self, site, spy, repo):
        spy.sync_result = twitch_control.BotOffline()
        repo.add(TwitchBotJoinChannel(twitch_id=TWITCH_ID, state="enabled"))
        _own_channel_session(site, repo)

        response = self._disable(site)

        assert response.json() == {"state": "disabled", "bot_offline": True}
        assert _channel(repo).state == "disabled"

    def test_already_disabled_syncs_again(self, site, spy, repo):
        repo.add(TwitchBotJoinChannel(twitch_id=TWITCH_ID, state="disabled"))
        _own_channel_session(site, repo)

        response = self._disable(site)

        assert response.json() == {"state": "disabled", "bot_offline": False}
        assert spy.sync_calls == [TWITCH_ID]

    @pytest.mark.parametrize("has_row", [True, False])
    def test_inactive_stays_inactive_without_sync(self, site, spy, repo, has_row):
        if has_row:
            repo.add(TwitchBotJoinChannel(twitch_id=TWITCH_ID, state="inactive"))
        _own_channel_session(site, repo)

        response = self._disable(site)

        assert response.json() == {"state": "inactive", "bot_offline": False}
        assert spy.sync_calls == []

    def test_other_channel_is_forbidden(self, site, spy, repo):
        repo.add(TwitchBotJoinChannel(twitch_id=TWITCH_ID, state="enabled"))
        site.cookies.set("dashboard_session", make_twitch_session(repo, twitch_id="777"))

        response = self._disable(site)

        assert response.status_code == 403
        assert response.json()["error"] == "channel_forbidden"
        assert _channel(repo).state == "enabled"
        assert spy.sync_calls == []

    def test_requires_allowed_origin(self, site, spy, repo):
        _own_channel_session(site, repo)

        response = site.post(f"/dashboard/channels/{CHANNEL}/disable", headers={"Origin": "https://evil.example"})

        assert response.status_code == 400
