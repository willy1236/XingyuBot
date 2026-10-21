"""實況主授權 Twitch bot：/to/twitchauth 與 /oauth/twitch（假的 Twitch 與 auth server，真實 PostgreSQL，交易結束後 rollback）。"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_identity import repo  # noqa: F401  (repo 為 fixture)

from starlib.database import TwitchBotJoinChannel
from starlib.identity import MemberUnknown, NotMember, TwitchMember
from starlib.oauth import TwitchOAuth
from starlib.providers.social.models import TwitchUser
from starServer import bot_website

TWITCH_ID = 2000000001
STATE = "state-abc"


class Spy:
    """記錄 TwitchOAuth 與 lookup 的呼叫，並替換成不連外的版本。"""

    def __init__(self):
        self.exchange_calls = 0
        self.lookup_calls: list[str] = []
        self.saved_tokens: list[str] = []
        self.lookup_result = TwitchMember(account_id=uuid4(), username="citizen")
        self.exchange_error: Exception | None = None
        self.get_me_error: Exception | None = None


def _twitch_user() -> TwitchUser:
    return TwitchUser(
        id=str(TWITCH_ID),
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
def spy(monkeypatch, repo) -> Spy:  # noqa: F811
    spy = Spy()

    async def exchange_code(self, code):
        spy.exchange_calls += 1
        if spy.exchange_error:
            raise spy.exchange_error
        return {}

    async def get_me(self):
        if spy.get_me_error:
            raise spy.get_me_error
        return _twitch_user()

    def save_token_to_db(self, user_id, token_data=None):
        spy.saved_tokens.append(user_id)

    async def lookup(twitch_id):
        spy.lookup_calls.append(str(twitch_id))
        return spy.lookup_result

    monkeypatch.setattr(TwitchOAuth, "exchange_code", exchange_code)
    monkeypatch.setattr(TwitchOAuth, "get_me", get_me)
    monkeypatch.setattr(TwitchOAuth, "save_token_to_db", save_token_to_db)
    monkeypatch.setattr(bot_website, "lookup_twitch_member", lookup)
    monkeypatch.setattr(bot_website, "sqldb", repo)
    return spy


@pytest.fixture
def client() -> TestClient:
    return TestClient(bot_website.app, base_url="https://testserver", follow_redirects=False)


def _callback(client: TestClient, *, state_cookie: str | None = STATE, **params):
    if state_cookie is not None:
        client.cookies.set("oauth_state", state_cookie)
    return client.get("/oauth/twitch", params=params)


def _assert_state_cookie_deleted(response):
    assert any(h.startswith("oauth_state=") and "Max-Age=0" in h for h in response.headers.get_list("set-cookie"))


class TestToTwitchAuth:
    def test_without_site_login_redirects_to_twitch(self, client, spy):
        response = client.get("/to/twitchauth")

        assert response.status_code == 307
        assert response.headers["location"].startswith("https://id.twitch.tv/oauth2/authorize")
        assert "oauth_state=" in response.headers["set-cookie"]


class TestMember:
    def test_saves_token_and_registers_channel(self, client, spy, repo):
        response = _callback(client, code="c", state=STATE)

        assert response.status_code == 200
        assert "/mod xingyu1016" in response.text
        assert "重啟" in response.text
        _assert_state_cookie_deleted(response)
        assert spy.saved_tokens == [str(TWITCH_ID)]
        assert spy.lookup_calls == [str(TWITCH_ID)]
        assert repo.get(TwitchBotJoinChannel, (TWITCH_ID,)) is not None

    def test_reauthorize_keeps_channel_settings(self, client, spy, repo):
        repo.merge(TwitchBotJoinChannel(twitch_id=TWITCH_ID, action_channel_id=123, point_name="星幣"))

        response = _callback(client, code="c", state=STATE)

        assert response.status_code == 200
        assert spy.saved_tokens == [str(TWITCH_ID)]
        channel = repo.get(TwitchBotJoinChannel, (TWITCH_ID,))
        repo.expire(channel)
        assert (channel.action_channel_id, channel.point_name) == (123, "星幣")

    def test_does_not_write_linked_account(self, client, spy, repo, monkeypatch):
        calls = []
        monkeypatch.setattr(repo, "upsert_linked_account", lambda *a, **k: calls.append((a, k)))

        response = _callback(client, code="c", state=STATE)

        assert response.status_code == 200
        assert calls == []


class TestRejected:
    def test_not_member_has_no_side_effects(self, client, spy, repo):
        spy.lookup_result = NotMember()
        repo.merge(TwitchBotJoinChannel(twitch_id=TWITCH_ID, action_channel_id=123, point_name="星幣"))

        response = _callback(client, code="c", state=STATE)

        assert response.status_code == 403
        assert "請先註冊析域帳號並在帳號頁連結這個 Twitch" in response.text
        assert 'href="https://auth.domalyze.net"' in response.text
        _assert_state_cookie_deleted(response)
        assert spy.saved_tokens == []
        channel = repo.get(TwitchBotJoinChannel, (TWITCH_ID,))
        repo.expire(channel)
        assert (channel.action_channel_id, channel.point_name) == (123, "星幣")

    def test_not_member_does_not_register_channel(self, client, spy, repo):
        spy.lookup_result = NotMember()

        _callback(client, code="c", state=STATE)

        assert repo.get(TwitchBotJoinChannel, (TWITCH_ID,)) is None

    def test_member_unknown_asks_to_retry(self, client, spy, repo):
        spy.lookup_result = MemberUnknown()

        response = _callback(client, code="c", state=STATE)

        assert response.status_code == 503
        assert "這次授權失敗，請稍後再試" in response.text
        _assert_state_cookie_deleted(response)
        assert spy.saved_tokens == []
        assert repo.get(TwitchBotJoinChannel, (TWITCH_ID,)) is None


class TestAuthorizationFailed:
    def test_missing_code(self, client, spy):
        response = _callback(client, state=STATE)

        assert response.status_code == 400
        assert spy.exchange_calls == 0

    def test_denied_by_user(self, client, spy):
        response = _callback(client, error="access_denied", state=STATE)

        assert response.status_code == 400
        assert "access_denied" in response.text
        assert spy.exchange_calls == 0

    def test_state_cookie_missing(self, client, spy):
        response = _callback(client, state_cookie=None, code="c", state=STATE)

        assert response.status_code == 400
        _assert_state_cookie_deleted(response)
        assert spy.exchange_calls == 0 and spy.lookup_calls == []

    def test_state_mismatch(self, client, spy):
        response = _callback(client, code="c", state="other")

        assert response.status_code == 400
        assert spy.exchange_calls == 0 and spy.lookup_calls == []

    @pytest.mark.parametrize("where", ["exchange_error", "get_me_error"])
    def test_twitch_failure_is_authorization_failure(self, client, spy, repo, where):
        setattr(spy, where, RuntimeError("twitch down"))

        response = _callback(client, code="c", state=STATE)

        assert response.status_code == 400
        _assert_state_cookie_deleted(response)
        assert spy.lookup_calls == [] and spy.saved_tokens == []
        assert repo.get(TwitchBotJoinChannel, (TWITCH_ID,)) is None


class TestStorageFailure:
    def test_token_save_error_shows_failure_page(self, client, spy, repo, monkeypatch):
        def broken_save(self, user_id, token_data=None):
            raise RuntimeError("db down")

        monkeypatch.setattr(TwitchOAuth, "save_token_to_db", broken_save)

        response = _callback(client, code="c", state=STATE)

        assert response.status_code == 503
        assert "這次授權失敗，請稍後再試" in response.text
        _assert_state_cookie_deleted(response)
        assert repo.get(TwitchBotJoinChannel, (TWITCH_ID,)) is None

    def test_channel_register_error_shows_failure_page(self, client, spy, repo, monkeypatch):
        def broken_add(*args, **kwargs):
            raise RuntimeError("db down")

        monkeypatch.setattr(repo, "add", broken_add)

        response = _callback(client, code="c", state=STATE)

        assert response.status_code == 503
        assert "這次授權失敗，請稍後再試" in response.text
        _assert_state_cookie_deleted(response)
