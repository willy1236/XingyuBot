"""OAuth2Base.save_token_to_db：重新授權存下的 token 一律清掉續期失敗的標記（O-05）。"""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from starlib.database import OAuthToken
from starlib.oauth import TwitchOAuth, oauth_lib


@pytest.fixture
def merged(monkeypatch) -> list[OAuthToken]:
    saved: list[OAuthToken] = []
    fake = SimpleNamespace(merge=saved.append, get_oauth_token=lambda user_id, credential_id: saved[-1])
    monkeypatch.setattr(oauth_lib, "sqldb", fake)
    return saved


def _auth() -> TwitchOAuth:
    client = SimpleNamespace(
        client_id="cid", client_secret="secret", redirect_uri="https://x.test/cb", default_scopes=[], credential_id=7
    )
    return TwitchOAuth.create_from_db(client)  # pyright: ignore[reportArgumentType]


def test_exchanged_token_clears_failure_mark(merged):
    auth = _auth()
    auth.db_token = auth.to_db_token({"access_token": "a", "refresh_token": "r", "expires_in": 60, "scope": ["x"]})  # pyright: ignore[reportArgumentType]
    auth.db_token.refresh_failed_at = datetime(2026, 1, 1, tzinfo=UTC)

    auth.save_token_to_db("42")

    assert merged[-1].refresh_failed_at is None


def test_token_data_clears_failure_mark(merged):
    _auth().save_token_to_db("42", {"access_token": "a", "refresh_token": "r", "expires_in": 60, "scope": ["x"]})  # pyright: ignore[reportArgumentType]

    assert merged[-1].refresh_failed_at is None
