"""starlib.twitch_tokens：實況主 token 的續期。用本機 DB 的 Twitch OAuth client #3，測試資料用獨有的 user_id，結束後刪除。"""

import asyncio
import threading
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from sqlmodel import delete

from starlib import twitch_tokens
from starlib.database import APIType, OAuthToken, sqldb
from starlib.twitch_tokens import TokenInvalid, broadcaster_token

TWITCH_ID = 900000000000000777


@pytest.fixture
def credential_id():
    client = sqldb.get_oauth_client(APIType.Twitch, twitch_tokens.BROADCASTER_CLIENT_SEQ)
    credential = client.credential_id
    sqldb.release_session()
    return credential


@pytest.fixture
def store(credential_id):
    """寫入／讀取測試用的 token，結束後刪除。"""

    def put(*, expires_in: timedelta | None, refresh: str | None = "refresh-0", access: str = "access-0"):
        sqldb.merge(
            OAuthToken(
                user_id=str(TWITCH_ID),
                client_credential_id=credential_id,
                access_token=access,
                refresh_token=refresh,
                scope=["moderation:read"],
                expires_at=None if expires_in is None else datetime.now(UTC) + expires_in,
            )
        )
        sqldb.release_session()

    def get() -> OAuthToken:
        token = sqldb.get_oauth_token(str(TWITCH_ID), credential_id)
        sqldb.session.refresh(token)
        sqldb.release_session()
        return token

    yield SimpleStore(put, get)
    sqldb.session.exec(
        delete(OAuthToken).where(OAuthToken.user_id == str(TWITCH_ID), OAuthToken.client_credential_id == credential_id)
    )
    sqldb.commit()
    sqldb.release_session()


class SimpleStore:
    def __init__(self, put, get):
        self.put, self.get = put, get


def twitch_response(status: int = 200, **body):
    payload = {
        "access_token": "access-1",
        "refresh_token": "refresh-1",
        "expires_in": 14000,
        "scope": ["moderation:read"],
    }
    return MagicMock(status_code=status, text=str(body), json=lambda: {**payload, **body})


@pytest.fixture
def post(monkeypatch):
    mock = MagicMock(side_effect=lambda *a, **k: twitch_response())
    monkeypatch.setattr(twitch_tokens.httpx, "post", mock)
    return mock


def run(coro):
    return asyncio.run(coro)


def test_valid_token_is_returned_without_refresh(store, post):
    store.put(expires_in=timedelta(hours=1))
    assert run(broadcaster_token(TWITCH_ID)) == "access-0"
    post.assert_not_called()


def test_token_expiring_within_ten_minutes_is_refreshed_and_saved(store, post):
    store.put(expires_in=timedelta(minutes=9))

    assert run(broadcaster_token(TWITCH_ID)) == "access-1"

    sent = post.call_args.kwargs["data"]
    assert sent["grant_type"] == "refresh_token"
    assert sent["refresh_token"] == "refresh-0"
    saved = store.get()
    assert (saved.access_token, saved.refresh_token) == ("access-1", "refresh-1")
    assert saved.expires_at - datetime.now(UTC) > timedelta(hours=3)


def test_token_without_expiry_is_refreshed(store, post):
    store.put(expires_in=None)
    assert run(broadcaster_token(TWITCH_ID)) == "access-1"


def test_no_token_is_missing(store, post):
    assert run(broadcaster_token(TWITCH_ID)) == TokenInvalid("missing")
    post.assert_not_called()


def test_token_without_refresh_token_is_missing(store, post):
    store.put(expires_in=timedelta(minutes=1), refresh=None)
    assert run(broadcaster_token(TWITCH_ID)) == TokenInvalid("missing")


@pytest.mark.parametrize("status", [400, 401])
def test_rejected_refresh_token_is_revoked_and_keeps_stored_token(store, post, status):
    store.put(expires_in=timedelta(minutes=1))
    post.side_effect = lambda *a, **k: twitch_response(status, message="Invalid refresh token")

    assert run(broadcaster_token(TWITCH_ID)) == TokenInvalid("revoked")
    assert store.get().access_token == "access-0"


def test_twitch_down_keeps_using_unexpired_token(store, post):
    store.put(expires_in=timedelta(minutes=5))
    post.side_effect = httpx.ConnectError("down")
    assert run(broadcaster_token(TWITCH_ID)) == "access-0"


def test_twitch_down_with_expired_token_is_unavailable(store, post):
    store.put(expires_in=timedelta(minutes=-1))
    post.side_effect = lambda *a, **k: twitch_response(503)
    assert run(broadcaster_token(TWITCH_ID)) == TokenInvalid("unavailable")


def test_concurrent_callers_refresh_once(store, post):
    """同時有多個呼叫（含不同 process 時同樣靠 DB 行鎖）只換一次，其餘等鎖後直接用新 token。"""
    store.put(expires_in=timedelta(minutes=1))

    def slow(*args, **kwargs):
        time.sleep(0.3)
        return twitch_response()

    post.side_effect = slow
    results: list[str | TokenInvalid] = []
    threads = [
        threading.Thread(target=lambda: results.append(twitch_tokens.broadcaster_token_blocking(TWITCH_ID)))
        for _ in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(15)

    assert results == ["access-1"] * 8
    assert post.call_count == 1


def test_unexpected_error_is_reported_as_unavailable_not_raised(monkeypatch):
    monkeypatch.setattr(twitch_tokens, "_broadcaster_token", MagicMock(side_effect=RuntimeError("db down")))

    assert twitch_tokens.broadcaster_token_blocking(TWITCH_ID) == TokenInvalid("unavailable")
    assert run(broadcaster_token(TWITCH_ID)) == TokenInvalid("unavailable")


class TestBotUserId:
    @pytest.fixture(autouse=True)
    def _reset(self, monkeypatch):
        monkeypatch.setattr(twitch_tokens, "_bot_user_id", None)

    def test_查到後快取(self, monkeypatch):
        get = MagicMock(return_value=SimpleNamespace(user_id="42"))
        monkeypatch.setattr(twitch_tokens, "sqldb", SimpleNamespace(get_bot_oauth_token=get))

        assert twitch_tokens.bot_user_id_blocking() == "42"
        assert twitch_tokens.bot_user_id_blocking() == "42"
        get.assert_called_once_with(APIType.Twitch, twitch_tokens.BOT_CLIENT_SEQ)

    def test_沒有_user_id_時_raise_且不快取(self, monkeypatch):
        get = MagicMock(side_effect=[SimpleNamespace(user_id=None), SimpleNamespace(user_id="42")])
        monkeypatch.setattr(twitch_tokens, "sqldb", SimpleNamespace(get_bot_oauth_token=get))

        with pytest.raises(RuntimeError):
            twitch_tokens.bot_user_id_blocking()
        assert twitch_tokens.bot_user_id_blocking() == "42"
