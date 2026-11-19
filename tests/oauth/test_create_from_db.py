"""OAuth2Base.create_from_db 的 scope 決定：None 用 DB 預設，空 list 代表不要任何 scope。"""

from types import SimpleNamespace

import pytest

from starlib.oauth import TwitchOAuth


def _client():
    return SimpleNamespace(
        client_id="cid",
        client_secret="secret",
        redirect_uri="https://x.test/cb",
        default_scopes=["a", "b"],
        credential_id=1,
    )


@pytest.mark.parametrize(("scopes", "expected"), [(None, ["a", "b"]), ([], []), (["c"], ["c"])])
def test_scopes_resolution(scopes, expected):
    auth = TwitchOAuth.create_from_db(_client(), scopes=scopes)

    assert auth.scopes == expected


def test_empty_scopes_authorization_url_has_no_scope_param():
    url, _ = TwitchOAuth.create_from_db(_client(), scopes=[]).get_authorization_url()

    assert "scope=" not in url
