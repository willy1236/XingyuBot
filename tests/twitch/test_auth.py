"""舊的實況主授權流程已關閉：/to/twitchauth 與沒有後台 cookie 的 /oauth/twitch 只引導到後台（真實 PostgreSQL，交易結束後 rollback）。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from starlib.database import OAuthToken, TwitchBotJoinChannel
from starServer import bot_website
from starServer.dashboard import config

FRONTEND = "https://domalyze.net"
LOGIN_URL = f"{FRONTEND}/dashboard-login"


@pytest.fixture(autouse=True)
def _frontend(monkeypatch):
    monkeypatch.setattr(config, "frontend_url", lambda: FRONTEND)


@pytest.fixture
def client() -> TestClient:
    return TestClient(bot_website.app, base_url="https://testserver", follow_redirects=False)


def test_to_twitchauth_redirects_to_dashboard_login(client):
    response = client.get("/to/twitchauth")

    assert response.status_code == 307
    assert response.headers["location"] == LOGIN_URL
    assert "set-cookie" not in response.headers


@pytest.mark.parametrize(
    "params",
    [{"code": "c", "state": "s"}, {"error": "access_denied"}, {}],
    ids=["with_code", "denied", "empty"],
)
def test_old_callback_asks_to_enable_in_dashboard(client, repo, params):
    before_channels = len(repo.session.exec(select(TwitchBotJoinChannel)).all())
    before_tokens = len(repo.session.exec(select(OAuthToken)).all())

    response = client.get("/oauth/twitch", params=params)

    assert response.status_code == 200
    assert "請到星羽後台啟用" in response.text
    assert LOGIN_URL in response.text
    assert len(repo.session.exec(select(TwitchBotJoinChannel)).all()) == before_channels
    assert len(repo.session.exec(select(OAuthToken)).all()) == before_tokens
