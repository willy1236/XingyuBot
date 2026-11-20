"""後台 session 支援 Twitch 身分：require_session／require_any_session、/dashboard/me、登出與 login_method 推導（真實 PostgreSQL）。"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from starlib.database import DashboardSession
from starServer.dashboard.session import TwitchIdentity, create_session
from tests.helpers.dashboard_auth import FRONTEND, USER_ID, make_app, make_session, make_twitch_session

pytestmark = pytest.mark.usefixtures("dashboard_env")

TWITCH = TwitchIdentity("777", "streamer", "Streamer", "https://static-cdn.jtvnw.net/777.png")


def client_for(session_id: str) -> TestClient:
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
    c.cookies.set("dashboard_session", session_id)
    return c


def remaining(repo) -> set[str]:
    repo.session.expire_all()
    return {row.session_id for row in repo.session.exec(select(DashboardSession)).all()}


class TestTwitchOnlySession:
    def test_me_returns_twitch_identity(self, repo):
        sid = make_twitch_session(repo)
        body = client_for(sid).get("/dashboard/me").json()
        assert body == {
            "id": "twitch:777",
            "name": "Streamer",
            "avatar_url": "https://static-cdn.jtvnw.net/777.png",
            "discord": None,
            "twitch": {"id": "777", "login": "streamer"},
            "account": None,
            "login_method": "twitch",
            "has_channels": True,
            "is_bot_owner": False,
        }

    @pytest.mark.parametrize(
        "path", ["/dashboard/guilds", "/dashboard/personal/drive", "/dashboard/personal/playlists"]
    )
    def test_discord_endpoints_return_403(self, repo, path):
        c = client_for(make_twitch_session(repo))
        r = c.get(path)
        assert r.status_code == 403 and r.json() == {"error": "discord_required"}

    def test_personal_overview_has_own_channel_only(self, repo):
        r = client_for(make_twitch_session(repo)).get("/dashboard/personal/overview")
        assert r.status_code == 200
        body = r.json()
        assert (body["account"], body["partial"], body["discords"]) == (None, False, [])
        assert [(c["id"], c["name"]) for c in body["channels"]] == [("777", "Streamer")]

    def test_no_account_follow(self, repo, dashboard_env):
        c = client_for(make_twitch_session(repo))
        assert c.get("/dashboard/me").status_code == 200
        assert dashboard_env.directory.calls == 0 and dashboard_env.directory.account_calls == 0

    def test_not_recorded_as_website_activity(self, repo):
        from starlib.database import WebsiteWeeklyActivity

        client_for(make_twitch_session(repo)).get("/dashboard/me")
        assert not repo.session.exec(select(WebsiteWeeklyActivity)).all()

    def test_unknown_session_is_401(self, repo):
        r = client_for("nope").get("/dashboard/me")
        assert r.status_code == 401 and r.json() == {"error": "session_expired"}


class TestDiscordSessionUnchanged:
    def test_me_has_discord_and_no_twitch(self, repo):
        body = client_for(make_session(repo)).get("/dashboard/me").json()
        assert body["id"] == USER_ID
        assert body["discord"] == {"id": USER_ID} and body["twitch"] is None
        assert body["login_method"] == "discord" and body["has_channels"] is False


class TestLogout:
    def test_twitch_logout_removes_all_sessions_of_that_account(self, repo):
        make_twitch_session(repo, twitch_id="777", session_id="t1")
        make_twitch_session(repo, twitch_id="777", session_id="t2")
        make_twitch_session(repo, twitch_id="888", session_id="other-twitch")
        make_session(repo, session_id="discord")
        r = client_for("t1").post("/dashboard/logout", headers={"Origin": FRONTEND})
        assert r.status_code == 200
        assert remaining(repo) == {"other-twitch", "discord"}

    def test_discord_logout_leaves_twitch_sessions(self, repo):
        make_session(repo, session_id="d1")
        make_session(repo, session_id="d2")
        make_twitch_session(repo, session_id="t1")
        assert client_for("d1").post("/dashboard/logout", headers={"Origin": FRONTEND}).status_code == 200
        assert remaining(repo) == {"t1"}


class TestCreateSession:
    def _row(self, repo, session_id) -> DashboardSession:
        repo.session.expire_all()
        return repo.session.get(DashboardSession, session_id)  # pyright: ignore[reportReturnType]

    def test_login_method_is_derived(self, repo):
        discord = create_session(USER_ID, "n", None)
        domalyze = create_session(USER_ID, "n", None, account_id=uuid4(), via_domalyze=True)
        twitch = create_session(None, TWITCH.name, TWITCH.avatar, twitch=TWITCH)
        assert self._row(repo, discord).login_method == "discord"
        row = self._row(repo, domalyze)
        assert (row.login_method, row.via_domalyze) == ("domalyze", True)
        row = self._row(repo, twitch)
        assert (row.login_method, row.via_domalyze, row.discord_user_id) == ("twitch", False, None)
        assert (row.twitch_user_id, row.twitch_login, row.twitch_name) == ("777", "streamer", "Streamer")

    def test_domalyze_session_without_discord(self, repo):
        sid = create_session(None, "n", None, account_id=uuid4(), via_domalyze=True)
        assert self._row(repo, sid).discord_user_id is None

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"discord_user_id": None},  # 沒有任何身分
            {"discord_user_id": USER_ID, "twitch": TWITCH},  # Twitch 登入不帶 Discord
            {"discord_user_id": None, "twitch": TWITCH, "via_domalyze": True},
        ],
    )
    def test_invalid_identity_rejected(self, repo, kwargs):
        with pytest.raises(ValueError):
            create_session(name="n", avatar=None, **kwargs)


class TestIdentityConstraint:
    def test_row_without_any_identity_is_rejected(self, repo):
        row = DashboardSession(session_id="bad", discord_user_id=None, name="n")
        with pytest.raises(IntegrityError):
            with repo.session.begin_nested():
                repo.session.add(row)
                repo.session.flush()
