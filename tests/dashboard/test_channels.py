"""實況主後台的頻道端點（W-01）：頻道清單、單一頻道、channel_forbidden 與 forward_access（真實 PostgreSQL）。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from starlib.database import TwitchBotJoinChannel
from starServer.dashboard import channels
from starServer.dashboard.channel_health import ChannelHealth
from starServer.dashboard.session import SessionInfo, TwitchIdentity
from tests.helpers.dashboard_auth import make_app, make_session, make_twitch_session

pytestmark = pytest.mark.usefixtures("dashboard_env")

CHANNEL_ID = "777"
HEALTH = ChannelHealth("partial", ("not_mod",), ("follow_response", "follow_forward"))


@pytest.fixture(autouse=True)
def _channels_db(monkeypatch, repo):
    monkeypatch.setattr(channels, "sqldb", repo)
    existing = repo.session.get(TwitchBotJoinChannel, int(CHANNEL_ID))
    if existing is not None:
        repo.session.delete(existing)
        repo.session.flush()


@pytest.fixture(autouse=True)
def _health(monkeypatch):
    # health 的判定會打 Twitch 與 bot，內容由 test_channel_health 驗；這裡只驗端點帶出它
    async def fake(twitch_id: int) -> ChannelHealth:
        return HEALTH

    monkeypatch.setattr(channels, "channel_health", fake)


def client_for(session_id: str) -> TestClient:
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
    c.cookies.set("dashboard_session", session_id)
    return c


class TestListChannels:
    def test_twitch_session_lists_own_channel_with_state(self, repo):
        repo.add(TwitchBotJoinChannel(twitch_id=int(CHANNEL_ID), state="enabled"))
        sid = make_twitch_session(repo, twitch_id=CHANNEL_ID)

        r = client_for(sid).get("/dashboard/channels")

        assert r.status_code == 200
        assert r.json() == {
            "channels": [
                {
                    "id": CHANNEL_ID,
                    "login": "streamer",
                    "name": "Streamer",
                    "avatar_url": f"https://static-cdn.jtvnw.net/{CHANNEL_ID}.png",
                    "state": "enabled",
                }
            ]
        }

    def test_channel_without_row_is_inactive(self, repo):
        r = client_for(make_twitch_session(repo, twitch_id=CHANNEL_ID)).get("/dashboard/channels")

        assert [c["state"] for c in r.json()["channels"]] == ["inactive"]

    def test_discord_session_has_no_channels(self, repo):
        r = client_for(make_session(repo)).get("/dashboard/channels")

        assert r.status_code == 200
        assert r.json() == {"channels": []}

    def test_requires_login(self):
        r = client_for("nope").get("/dashboard/channels")

        assert r.status_code == 401 and r.json() == {"error": "session_expired"}


class TestGetChannel:
    def test_returns_channel_state_forward_access_and_health(self, repo):
        sid = make_twitch_session(repo, twitch_id=CHANNEL_ID)

        r = client_for(sid).get(f"/dashboard/channels/{CHANNEL_ID}")

        assert r.status_code == 200
        body = r.json()
        assert (body["id"], body["login"], body["name"], body["state"]) == (
            CHANNEL_ID,
            "streamer",
            "Streamer",
            "inactive",
        )
        assert body["forward_access"] == "need_domalyze"
        assert body["health"] == {
            "state": "partial",
            "issues": ["not_mod"],
            "paused_features": ["follow_response", "follow_forward"],
        }

    def test_other_channel_is_forbidden(self, repo):
        sid = make_twitch_session(repo, twitch_id=CHANNEL_ID)

        r = client_for(sid).get("/dashboard/channels/888")

        assert r.status_code == 403 and r.json() == {"error": "channel_forbidden"}

    def test_discord_session_is_forbidden(self, repo):
        r = client_for(make_session(repo)).get(f"/dashboard/channels/{CHANNEL_ID}")

        assert r.status_code == 403 and r.json() == {"error": "channel_forbidden"}

    def test_requires_login(self):
        r = client_for("nope").get(f"/dashboard/channels/{CHANNEL_ID}")

        assert r.status_code == 401 and r.json() == {"error": "session_expired"}


def _info(login_method: str, discord_user_id: str | None) -> SessionInfo:
    return SessionInfo(
        "sid", discord_user_id, "n", None, login_method=login_method, twitch=TwitchIdentity("1", "l", "n", None)
    )


@pytest.mark.parametrize(
    ("login_method", "discord_user_id", "expected"),
    [
        ("twitch", None, "need_domalyze"),
        ("discord", "1", "need_domalyze"),
        ("domalyze", "1", "ok"),
        ("domalyze", None, "need_discord"),
    ],
)
def test_forward_access(login_method, discord_user_id, expected):
    assert channels.forward_access(_info(login_method, discord_user_id)) == expected


class TestBanned:
    def test_停權的頻道_清單與詳情的_state_都是_banned(self, repo):
        repo.add(
            TwitchBotJoinChannel(
                twitch_id=int(CHANNEL_ID), state="disabled", banned_at=datetime(2026, 1, 1, tzinfo=UTC)
            )
        )
        sid = make_twitch_session(repo, twitch_id=CHANNEL_ID)

        assert client_for(sid).get("/dashboard/channels").json()["channels"][0]["state"] == "banned"
        assert client_for(sid).get(f"/dashboard/channels/{CHANNEL_ID}").json()["state"] == "banned"
