"""析域登入的 session 帶入析域帳號連結的 Twitch 頻道（W-10）：60 秒內跟隨增減、auth server 不可用、補頻道列、失效規則（假 auth server，真實 PostgreSQL）。"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from starlib import sclient
from starlib.database import DashboardSession, TwitchBotJoinChannel
from starlib.identity import Account, LinkedPassport, ResolvedAccount
from starServer.dashboard import channels, session
from tests.helpers.accounts import FakeBot, account
from tests.helpers.dashboard_auth import FRONTEND, USER_ID, make_app, make_domalyze_session, make_session

pytestmark = pytest.mark.usefixtures("dashboard_env")

CHANNEL_A, CHANNEL_B = 7001, 7002


def linked(account_id, twitch=(), discord_ids=(int(USER_ID),), suspended=False) -> Account:
    base = account(account_id, discord_ids=discord_ids, suspended=suspended)
    return replace(base, twitch_passports=tuple(LinkedPassport(str(i), name) for i, name in twitch))


class Clock:
    def __init__(self):
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch) -> Clock:
    c = Clock()
    monkeypatch.setattr(session, "time", SimpleNamespace(monotonic=c.monotonic))
    return c


@pytest.fixture(autouse=True)
def _channel_rows(monkeypatch, repo):
    monkeypatch.setattr(channels, "sqldb", repo)
    for twitch_id in (CHANNEL_A, CHANNEL_B):
        row = repo.session.get(TwitchBotJoinChannel, twitch_id)
        if row is not None:
            repo.session.delete(row)
    repo.session.flush()


@pytest.fixture
def directory(dashboard_env):
    return dashboard_env.directory


def client_for(session_id: str) -> TestClient:
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
    c.cookies.set("dashboard_session", session_id)
    return c


def channel_ids(c: TestClient) -> list[str]:
    return [ch["id"] for ch in c.get("/dashboard/channels").json()["channels"]]


def link(directory, acc: Account) -> None:
    directory.by_account_id[acc.account_id] = ResolvedAccount(acc)


class TestChannelsFollowed:
    def test_lists_all_linked_twitch_channels_with_names(self, repo, directory, clock):
        acc = linked(uuid4(), twitch=[(CHANNEL_B, "Bravo"), (CHANNEL_A, "Alpha")])
        link(directory, acc)
        c = client_for(make_domalyze_session(repo, acc.account_id))

        body = c.get("/dashboard/channels").json()

        assert [(ch["id"], ch["name"], ch["state"]) for ch in body["channels"]] == [
            (str(CHANNEL_A), "Alpha", "inactive"),
            (str(CHANNEL_B), "Bravo", "inactive"),
        ]
        assert c.get(f"/dashboard/channels/{CHANNEL_A}").status_code == 200
        assert c.get("/dashboard/me").json()["has_channels"] is True

    def test_adds_missing_rows_as_inactive_and_keeps_existing_rows(self, repo, directory, clock):
        repo.add(
            TwitchBotJoinChannel(
                twitch_id=CHANNEL_A,
                state="enabled",
                login="alpha",
                display_name="Alpha Real",
                avatar_url="https://a/1.png",
            )
        )
        acc = linked(uuid4(), twitch=[(CHANNEL_A, "from passport"), (CHANNEL_B, "Bravo")])
        link(directory, acc)
        c = client_for(make_domalyze_session(repo, acc.account_id))

        by_id = {ch["id"]: ch for ch in c.get("/dashboard/channels").json()["channels"]}

        assert by_id[str(CHANNEL_A)] == {
            "id": str(CHANNEL_A),
            "login": "alpha",
            "name": "Alpha Real",
            "avatar_url": "https://a/1.png",
            "role": "owner",
            "state": "enabled",
        }
        repo.session.expire_all()
        row_b = repo.session.get(TwitchBotJoinChannel, CHANNEL_B)
        assert (row_b.state, row_b.display_name) == ("inactive", "Bravo") and row_b.first_seen_at is not None
        assert repo.session.get(TwitchBotJoinChannel, CHANNEL_A).state == "enabled"

    def test_existing_rows_are_not_written_again(self, repo, directory, clock, monkeypatch):
        repo.add(TwitchBotJoinChannel(twitch_id=CHANNEL_A, state="inactive", display_name="Alpha"))
        acc = linked(uuid4(), twitch=[(CHANNEL_A, "Alpha")])
        link(directory, acc)
        c = client_for(make_domalyze_session(repo, acc.account_id))
        monkeypatch.setattr(session, "pg_insert", lambda *_: pytest.fail("列都在時不該 INSERT"))

        assert channel_ids(c) == [str(CHANNEL_A)]

    def test_non_numeric_passport_is_skipped(self, repo, directory, clock):
        acc = linked(uuid4(), twitch=[(CHANNEL_A, "Alpha")])
        acc = replace(acc, twitch_passports=(*acc.twitch_passports, LinkedPassport("abc", "bad")))
        link(directory, acc)
        c = client_for(make_domalyze_session(repo, acc.account_id))

        assert channel_ids(c) == [str(CHANNEL_A)]

    def test_unlink_takes_effect_within_60_seconds(self, repo, directory, clock):
        acc = linked(uuid4(), twitch=[(CHANNEL_A, "Alpha"), (CHANNEL_B, "Bravo")])
        link(directory, acc)
        c = client_for(make_domalyze_session(repo, acc.account_id))
        assert channel_ids(c) == [str(CHANNEL_A), str(CHANNEL_B)]

        link(directory, linked(acc.account_id, twitch=[(CHANNEL_A, "Alpha")]))
        clock.now += 59
        assert channel_ids(c) == [str(CHANNEL_A), str(CHANNEL_B)]
        clock.now += 2
        assert channel_ids(c) == [str(CHANNEL_A)]
        r = c.get(f"/dashboard/channels/{CHANNEL_B}")
        assert (r.status_code, r.json()) == (403, {"error": "channel_forbidden"})

    def test_new_link_takes_effect_within_60_seconds(self, repo, directory, clock):
        acc = linked(uuid4(), twitch=[(CHANNEL_A, "Alpha")])
        link(directory, acc)
        c = client_for(make_domalyze_session(repo, acc.account_id))
        assert channel_ids(c) == [str(CHANNEL_A)]

        link(directory, linked(acc.account_id, twitch=[(CHANNEL_A, "Alpha"), (CHANNEL_B, "Bravo")]))
        clock.now += 61

        assert channel_ids(c) == [str(CHANNEL_A), str(CHANNEL_B)]

    def test_auth_server_unavailable_keeps_last_list(self, repo, directory, clock):
        acc = linked(uuid4(), twitch=[(CHANNEL_A, "Alpha")])
        link(directory, acc)
        c = client_for(make_domalyze_session(repo, acc.account_id))
        assert channel_ids(c) == [str(CHANNEL_A)]

        directory.account_unavailable = True
        clock.now += 61

        assert channel_ids(c) == [str(CHANNEL_A)]

    def test_unavailable_without_previous_result_is_empty_but_not_revoked(self, repo, directory, clock, monkeypatch):
        acc = linked(uuid4(), twitch=[(CHANNEL_A, "Alpha")])
        link(directory, acc)
        c = client_for(make_domalyze_session(repo, acc.account_id))
        monkeypatch.setattr(session, "_followed", {})
        directory.account_unavailable = True

        r = c.get("/dashboard/channels")

        assert (r.status_code, r.json()) == (200, {"channels": []})

    def test_discord_login_with_linked_account_has_no_channels(self, repo, directory, clock):
        acc = linked(uuid4(), twitch=[(CHANNEL_A, "Alpha")])
        directory.accounts[int(USER_ID)] = acc
        c = client_for(make_session(repo))

        assert channel_ids(c) == []
        assert c.get("/dashboard/me").json()["has_channels"] is False


class TestRevocationWithoutDiscord:
    @pytest.fixture
    def acc(self, directory):
        acc = linked(uuid4(), twitch=[(CHANNEL_A, "Alpha")], discord_ids=())
        link(directory, acc)
        return acc

    def test_session_without_discord_stays_while_account_has_only_twitch(self, repo, acc, clock):
        c = client_for(make_domalyze_session(repo, acc.account_id, user_id=None))
        clock.now += 61

        assert channel_ids(c) == [str(CHANNEL_A)]

    @pytest.mark.parametrize("change", ["suspended", "not_found"])
    def test_session_without_discord_is_revoked_when_account_gone(self, repo, directory, acc, clock, change):
        c = client_for(make_domalyze_session(repo, acc.account_id, user_id=None))
        if change == "suspended":
            link(directory, linked(acc.account_id, twitch=[(CHANNEL_A, "Alpha")], discord_ids=(), suspended=True))
        else:
            directory.by_account_id.clear()
        clock.now += 61

        r = c.get("/dashboard/channels")

        assert (r.status_code, r.json()) == (401, {"error": "session_expired"})
        repo.session.expire_all()
        assert repo.session.get(DashboardSession, "dsid") is None

    def test_session_with_discord_is_still_revoked_when_discord_unlinked(self, repo, directory, clock):
        acc = linked(uuid4(), twitch=[(CHANNEL_A, "Alpha")], discord_ids=(int(USER_ID),))
        link(directory, acc)
        c = client_for(make_domalyze_session(repo, acc.account_id))
        link(directory, linked(acc.account_id, twitch=[(CHANNEL_A, "Alpha")], discord_ids=()))
        clock.now += 61

        assert c.get("/dashboard/channels").status_code == 401


class TestLogoutWithoutDiscord:
    def test_removes_discordless_domalyze_sessions_of_that_account_only(self, repo, directory):
        mine, other = uuid4(), uuid4()
        link(directory, linked(mine, twitch=[(CHANNEL_A, "Alpha")], discord_ids=()))
        make_domalyze_session(repo, mine, user_id=None, session_id="d1")
        make_domalyze_session(repo, mine, user_id=None, session_id="d2")
        make_domalyze_session(repo, other, user_id=None, session_id="other-account")
        make_domalyze_session(repo, mine, user_id=USER_ID, session_id="with-discord")

        r = client_for("d1").post("/dashboard/logout", headers={"Origin": FRONTEND})

        assert r.status_code == 200
        repo.session.expire_all()
        ids = {"d1", "d2", "other-account", "with-discord"}
        assert {sid for sid in ids if repo.session.get(DashboardSession, sid) is not None} == {
            "other-account",
            "with-discord",
        }


class TestPersonalOverview:
    def test_without_discord_has_channels_and_no_discords(self, repo, directory, clock):
        acc = linked(uuid4(), twitch=[(CHANNEL_A, "Alpha")], discord_ids=())
        link(directory, acc)
        c = client_for(make_domalyze_session(repo, acc.account_id, user_id=None))

        r = c.get("/dashboard/personal/overview")

        assert r.status_code == 200
        body = r.json()
        assert (body["account"], body["partial"], body["discords"]) == ({"username": "willy"}, False, [])
        assert [(ch["id"], ch["name"], ch["state"]) for ch in body["channels"]] == [
            (str(CHANNEL_A), "Alpha", "inactive")
        ]

    def test_with_discord_has_discords_and_channels(self, repo, directory, clock, monkeypatch):
        monkeypatch.setattr(sclient, "bot", FakeBot({int(USER_ID): ("Some One", None)}))
        acc = linked(uuid4(), twitch=[(CHANNEL_A, "Alpha"), (CHANNEL_B, "Bravo")])
        link(directory, acc)
        c = client_for(make_domalyze_session(repo, acc.account_id))

        body = c.get("/dashboard/personal/overview").json()

        assert [d["id"] for d in body["discords"]] == [USER_ID]
        assert [ch["id"] for ch in body["channels"]] == [str(CHANNEL_A), str(CHANNEL_B)]

    @pytest.mark.parametrize(
        "path", ["/dashboard/personal/drive", "/dashboard/personal/playlists", "/dashboard/guilds"]
    )
    def test_other_endpoints_still_need_discord(self, repo, directory, clock, path):
        acc = linked(uuid4(), twitch=[(CHANNEL_A, "Alpha")], discord_ids=())
        link(directory, acc)
        c = client_for(make_domalyze_session(repo, acc.account_id, user_id=None))

        r = c.get(path)

        assert (r.status_code, r.json()) == (403, {"error": "discord_required"})


class TestForwardAccess:
    def test_domalyze_login_with_discord_can_forward(self, repo, directory, clock):
        acc = linked(uuid4(), twitch=[(CHANNEL_A, "Alpha")])
        link(directory, acc)
        c = client_for(make_domalyze_session(repo, acc.account_id))

        assert c.get(f"/dashboard/channels/{CHANNEL_A}").json()["forward_access"] == "ok"

    def test_domalyze_login_without_discord_needs_discord(self, repo, directory, clock):
        acc = linked(uuid4(), twitch=[(CHANNEL_A, "Alpha")], discord_ids=())
        link(directory, acc)
        c = client_for(make_domalyze_session(repo, acc.account_id, user_id=None))

        assert c.get(f"/dashboard/channels/{CHANNEL_A}").json()["forward_access"] == "need_discord"
