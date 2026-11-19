"""個人區：可見範圍的共用判斷與 /dashboard/personal/overview（假 auth server、假 bot，真實 PostgreSQL）。"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from starlib import sclient
from starlib.database import DashboardSession, Pet, UserPoint
from starlib.fileDatabase import Jsondb
from starlib.identity import BotIdentity, IdentityUnavailable
from starServer.dashboard import auth, personal
from starServer.dashboard.personal import PersonalScope, personal_scope, require_personal
from starServer.dashboard.session import SessionInfo
from tests.accounts.personal_helpers import OWN, directory, identity  # noqa: F401  (fixture)
from tests.helpers.accounts import OTHER_ID, FakeBot, account
from tests.helpers.dashboard_auth import FRONTEND, USER_ID, make_app, make_session

pytestmark = pytest.mark.usefixtures("dashboard_env")

OTHER = int(OTHER_ID)
HEADERS = {"Origin": FRONTEND}


def scope_of(info: SessionInfo) -> PersonalScope:
    return asyncio.run(personal_scope(info))


class TestPersonalScope:
    def test_with_account(self, identity):
        acc_id = uuid4()
        info = SessionInfo(
            "sid", USER_ID, "n", None, account_id=acc_id, account_username="willy", discord_ids=(OWN, OTHER)
        )
        assert scope_of(info) == PersonalScope(acc_id, "willy", [OWN, OTHER], False, acc_id, True, False)

    def test_partial_when_stale_and_only_own(self, identity):
        acc_id = uuid4()
        info = SessionInfo("sid", USER_ID, "n", None, account_id=acc_id, discord_ids=(OWN,), stale=True)
        s = scope_of(info)
        assert s.partial and s.discord_ids == [OWN] and s.account_username is None

    def test_stale_but_previous_result_not_partial(self, identity):
        info = SessionInfo("sid", USER_ID, "n", None, account_id=uuid4(), discord_ids=(OWN, OTHER), stale=True)
        assert not scope_of(info).partial

    def test_without_account_uses_temporary_id(self, identity):
        temp = uuid4()
        identity["result"] = BotIdentity(temp, False, None, (), False)
        s = scope_of(SessionInfo("sid", USER_ID, "n", None))
        assert s == PersonalScope(None, None, [OWN], False, temp, False, False)

    def test_without_any_record(self, identity):
        s = scope_of(SessionInfo("sid", USER_ID, "n", None))
        assert (s.tool_user_id, s.tool_unavailable) == (None, False)

    def test_identity_unavailable(self, identity):
        identity["result"] = IdentityUnavailable()
        s = scope_of(SessionInfo("sid", USER_ID, "n", None))
        assert (s.tool_user_id, s.tool_unavailable, s.tools_writable) == (None, True, False)


@pytest.fixture
def client(repo, identity, monkeypatch) -> TestClient:
    monkeypatch.setattr(personal, "sqldb", repo)
    monkeypatch.setattr(sclient, "bot", FakeBot({OWN: ("Some One", "abc"), OTHER: ("Other", None)}))
    app = make_app()

    @app.post("/dashboard/probe-write")
    async def probe(scope: PersonalScope = Depends(require_personal(write=True))):
        return {"ok": True}

    c = TestClient(app, base_url="https://testserver", follow_redirects=False)
    make_session(repo)
    c.cookies.set("dashboard_session", "sid")
    return c


class TestRequirePersonal:
    def test_write_requires_account(self, client):
        res = client.post("/dashboard/probe-write", headers=HEADERS)
        assert (res.status_code, res.json()) == (403, {"error": "domalyze_required"})

    def test_write_with_account(self, client, directory):
        directory.accounts[OWN] = account(uuid4())
        assert client.post("/dashboard/probe-write", headers=HEADERS).json() == {"ok": True}


class TestOverview:
    def seed(self, repo):
        repo.session.merge(UserPoint(discord_id=OWN, stardust=10, point=2, rcoin=3))
        repo.session.merge(Pet(discord_id=OTHER, pet_species="shark", pet_name="鯊鯊", food=20))
        repo.session.commit()

    def test_without_account(self, client, repo):
        self.seed(repo)
        assert client.get("/dashboard/personal/overview").json() == {
            "account": None,
            "partial": False,
            "discords": [
                {
                    "id": USER_ID,
                    "name": "Some One",
                    "avatar_url": auth.avatar_url(USER_ID, "abc"),
                    "current": True,
                    "points": {"stardust": 10, "point": 2, "rcoin": 3},
                    "pet": None,
                }
            ],
        }

    def test_with_two_discords(self, client, directory, repo):
        self.seed(repo)
        directory.accounts[OWN] = account(uuid4(), discord_ids=(OWN, OTHER))
        body = client.get("/dashboard/personal/overview").json()
        assert body["account"] == {"username": "willy"} and body["partial"] is False
        assert [(d["id"], d["name"], d["current"]) for d in body["discords"]] == [
            (USER_ID, "Some One", True),
            (OTHER_ID, "Other", False),
        ]
        other = body["discords"][1]
        assert other["points"] == {"stardust": 0, "point": 0, "rcoin": 0}
        assert other["pet"] == {"name": "鯊鯊", "species": Jsondb.get_tw("shark", "pet_option"), "food": 20}

    def test_partial(self, client, directory, repo):
        row = repo.session.get(DashboardSession, "sid")
        row.account_id = uuid4()
        repo.session.add(row)
        repo.session.commit()
        directory.unavailable = True
        body = client.get("/dashboard/personal/overview").json()
        assert body["account"] == {"username": None} and body["partial"] is True
        assert [d["id"] for d in body["discords"]] == [USER_ID]

    def test_discord_user_unavailable_falls_back_to_session(self, client):
        sclient.bot = FakeBot({})
        [d] = client.get("/dashboard/personal/overview").json()["discords"]
        assert (d["name"], d["avatar_url"]) == ("Some One", auth.avatar_url(USER_ID, None))

    def test_requires_session(self, identity):
        c = TestClient(make_app(), base_url="https://testserver")
        assert c.get("/dashboard/personal/overview").json() == {"error": "session_expired"}
