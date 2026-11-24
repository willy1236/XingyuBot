"""C-08：啟用流程向實況主要 `channel:manage:broadcast`（新啟用的頻道在啟用時就授權改標題）。"""

from urllib.parse import parse_qs, urlparse

import pytest

from starlib import twitch_tokens
from starServer.dashboard import channel_activation
from tests.dashboard.test_channel_activation import (
    CHANNEL,
    FRONTEND,
    Spy,  # noqa: F401
    _callback,
    _no_channel,  # noqa: F401 (fixture)
    _own_channel_session,
    site,  # noqa: F401 (fixture)
    spy,  # noqa: F401 (fixture)
)

pytestmark = pytest.mark.usefixtures("dashboard_env")


def expected_scopes():
    return [*channel_activation.ENABLE_SCOPES, *twitch_tokens.STREAM_INFO_SCOPES]


def test_導向_Twitch_的授權要求含改標題權限(site, spy, repo):
    _own_channel_session(site, repo)

    response = site.get("/to/dashboard-twitch-enable", params={"channel": CHANNEL, "origin": FRONTEND})

    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["scope"] == [" ".join(expected_scopes())]
    assert "channel:manage:broadcast" in query["scope"][0].split()


def test_啟用時換取_token_用含改標題權限的_scope(site, spy, repo):
    _own_channel_session(site, repo)

    _callback(site, code="c")

    assert spy.scopes == [expected_scopes()]
