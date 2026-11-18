"""個人區雲端資料夾共用：資格、設定、更換、取消、驗證與失敗（假 Google API、假 bot，真實 PostgreSQL）。"""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_dashboard_auth import FRONTEND, USER_ID, dashboard_env, make_app, make_session  # noqa: F401
from test_dashboard_domalyze_login import OTHER_ID, account
from test_dashboard_personal import directory, identity  # noqa: F401
from test_identity import repo  # noqa: F401

from starlib import drive_share, sclient
from starlib.database import DriveShare
from starlib.identity import BotIdentity, IdentityUnavailable
from starServer.dashboard import personal, personal_drive

OWN = int(USER_ID)
OTHER = int(OTHER_ID)
HEADERS = {"Origin": FRONTEND}
GUILD = 111


class FakeGuild:
    def __init__(self, members: set[int]):
        self.members = members

    def get_member(self, uid: int):
        return object() if uid in self.members else None


class FakeBot:
    def __init__(self, guilds: dict[int, FakeGuild], ready: bool = True):
        self.guilds = guilds
        self.ready = ready
        self._pool = ThreadPoolExecutor(max_workers=1)

    def is_ready(self):
        return self.ready

    def get_guild(self, gid: int):
        return self.guilds.get(gid)

    def get_user(self, uid: int):
        return None

    async def fetch_user(self, uid: int):
        return SimpleNamespace(global_name="x", name="x", avatar=None)

    def submit(self, coro):
        return self._pool.submit(asyncio.run, coro)


class FakeGoogle:
    """記錄呼叫的 XingyuGoogleCloud 替身，不連正式 API。"""

    fail_add = False
    fail_remove_ids: set[str] = set()
    permissions: dict[str, str] = {}  # permission id -> email
    calls: list[tuple] = []
    threads: set[str] = set()
    counter = 0

    @classmethod
    def reset(cls):
        cls.fail_add, cls.fail_remove_ids, cls.permissions, cls.calls, cls.threads, cls.counter = (
            False,
            set(),
            {},
            [],
            set(),
            0,
        )

    def add_file_permissions(self, file_id, email):
        type(self).calls.append(("add", email))
        type(self).threads.add(threading.current_thread().name)
        if self.fail_add:
            raise RuntimeError("google down")
        type(self).counter += 1
        pid = f"p{self.counter}"
        type(self).permissions[pid] = email
        return {"id": pid}

    def remove_file_permissions(self, file_id, permission_id):
        type(self).calls.append(("remove", permission_id))
        type(self).threads.add(threading.current_thread().name)
        if permission_id in self.fail_remove_ids:
            raise RuntimeError("google down")
        type(self).permissions.pop(permission_id, None)


@pytest.fixture
def google(monkeypatch, repo):  # noqa: F811
    FakeGoogle.reset()
    monkeypatch.setattr(drive_share, "XingyuGoogleCloud", FakeGoogle)
    monkeypatch.setattr(drive_share, "sqldb", repo)
    monkeypatch.setattr(personal_drive, "sqldb", repo)
    return FakeGoogle


@pytest.fixture
def bot(monkeypatch):
    b = FakeBot({GUILD: FakeGuild({OWN})})
    monkeypatch.setattr(sclient, "bot", b)
    monkeypatch.setattr(personal_drive, "drive_share_guilds", [GUILD])
    return b


@pytest.fixture
def client(repo, identity, google, bot, monkeypatch) -> TestClient:  # noqa: F811
    monkeypatch.setattr(personal, "sqldb", repo)
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
    make_session(repo)
    c.cookies.set("dashboard_session", "sid")
    return c


def share(repo, user_id, gmail="old@gmail.com", share_id="old-id"):  # noqa: F811
    repo.session.merge(DriveShare(user_id=user_id, gmail=gmail, share_id=share_id))
    repo.session.commit()


def put(client, gmail):
    return client.put("/dashboard/personal/drive", json={"gmail": gmail}, headers=HEADERS)


@pytest.fixture
def acc(directory):  # noqa: F811
    a = uuid4()
    directory.accounts[OWN] = account(a)
    return a


class TestNormalize:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("abc", "abc@gmail.com"),
            ("abc@gmail.com", "abc@gmail.com"),
            ("ABC@GMAIL.COM", "ABC@GMAIL.COM"),
            (" abc ", "abc@gmail.com"),
        ],
    )
    def test_valid(self, raw, expected):
        assert drive_share.normalize_gmail(raw) == expected

    @pytest.mark.parametrize("raw", ["abc@yahoo.com", "a b", "", "@gmail.com", "a@b@gmail.com", "abc@gmail.com.tw"])
    def test_invalid(self, raw):
        assert drive_share.normalize_gmail(raw) is None


class TestEligibility:
    def test_member_of_enabled_guild(self, client, acc):
        body = client.get("/dashboard/personal/drive").json()
        assert body == {"writable": True, "unavailable": False, "eligible": True, "gmail": None}

    def test_not_in_any_enabled_guild(self, client, acc, bot):
        bot.guilds[GUILD].members.clear()
        body = client.get("/dashboard/personal/drive").json()
        assert (body["eligible"], body["gmail"]) == (False, None)

    def test_linked_discord_counts(self, client, directory, bot):  # noqa: F811
        a = uuid4()
        directory.accounts[OWN] = account(a, discord_ids=[OWN, OTHER])
        bot.guilds[GUILD].members.clear()
        bot.guilds[GUILD].members.add(OTHER)
        assert client.get("/dashboard/personal/drive").json()["eligible"] is True

    def test_bot_not_in_guild(self, client, acc, bot):
        bot.guilds.clear()
        assert client.get("/dashboard/personal/drive").json()["eligible"] is False

    def test_bot_unavailable(self, client, acc, bot):
        bot.ready = False
        res = client.get("/dashboard/personal/drive")
        assert (res.status_code, res.json()) == (503, {"error": "bot_unavailable"})

    def test_write_rejected_when_not_eligible(self, client, acc, bot, google):
        bot.guilds[GUILD].members.clear()
        res = put(client, "abc")
        assert (res.status_code, res.json()) == (403, {"error": "not_eligible"})
        assert google.calls == []


class TestSet:
    def test_set_appends_gmail_domain(self, client, acc, repo, google):  # noqa: F811
        body = put(client, "abc").json()
        assert body["gmail"] == "abc@gmail.com"
        row = repo.get_drive_share(acc)
        assert (row.gmail, row.share_id) == ("abc@gmail.com", "p1")
        assert google.calls == [("add", "abc@gmail.com")]

    def test_full_gmail_kept(self, client, acc):
        assert put(client, "abc@gmail.com").json()["gmail"] == "abc@gmail.com"

    def test_invalid_gmail(self, client, acc, google, repo):  # noqa: F811
        res = put(client, "abc@yahoo.com")
        assert (res.status_code, res.json()) == (400, {"error": "invalid_gmail"})
        assert google.calls == [] and repo.get_drive_share(acc) is None

    def test_replace_adds_new_then_removes_old(self, client, acc, repo, google):  # noqa: F811
        share(repo, acc)
        body = put(client, "new").json()
        assert body["gmail"] == "new@gmail.com"
        assert google.calls == [("add", "new@gmail.com"), ("remove", "old-id")]
        repo.session.expire_all()
        assert repo.get_drive_share(acc).share_id == "p1"

    def test_same_gmail_is_noop(self, client, acc, repo, google):  # noqa: F811
        share(repo, acc, "Abc@gmail.com", "pid")
        body = put(client, "abc@gmail.com").json()
        assert body["gmail"] == "Abc@gmail.com"
        assert google.calls == []

    def test_add_failure_keeps_original(self, client, acc, repo, google):  # noqa: F811
        share(repo, acc)
        google.fail_add = True
        res = put(client, "new")
        assert (res.status_code, res.json()) == (502, {"error": "drive_failed"})
        repo.session.expire_all()
        assert repo.get_drive_share(acc).gmail == "old@gmail.com"

    def test_remove_old_failure_revokes_new_and_keeps_original(self, client, acc, repo, google):  # noqa: F811
        share(repo, acc)
        google.fail_remove_ids = {"old-id"}
        res = put(client, "new")
        assert (res.status_code, res.json()) == (502, {"error": "drive_failed"})
        assert google.calls == [("add", "new@gmail.com"), ("remove", "old-id"), ("remove", "p1")]
        assert google.permissions == {}
        repo.session.expire_all()
        row = repo.get_drive_share(acc)
        assert (row.gmail, row.share_id) == ("old@gmail.com", "old-id")

    def test_requires_account(self, client, identity, google):  # noqa: F811
        identity["result"] = BotIdentity(uuid4(), False, None, (), False)
        res = put(client, "abc")
        assert (res.status_code, res.json()) == (403, {"error": "domalyze_required"})
        assert google.calls == []

    def test_requires_origin(self, client, acc):
        assert client.put("/dashboard/personal/drive", json={"gmail": "abc"}).status_code == 400


class TestRemove:
    def test_remove(self, client, acc, repo, google):  # noqa: F811
        share(repo, acc)
        res = client.delete("/dashboard/personal/drive", headers=HEADERS)
        assert res.json()["gmail"] is None
        assert google.calls == [("remove", "old-id")]
        repo.session.expire_all()
        assert repo.get_drive_share(acc) is None

    def test_remove_when_none_is_noop(self, client, acc, google):
        res = client.delete("/dashboard/personal/drive", headers=HEADERS)
        assert (res.status_code, res.json()["gmail"]) == (200, None)
        assert google.calls == []

    def test_remove_failure_keeps_setting(self, client, acc, repo, google):  # noqa: F811
        share(repo, acc)
        google.fail_remove_ids = {"old-id"}
        res = client.delete("/dashboard/personal/drive", headers=HEADERS)
        assert (res.status_code, res.json()) == (502, {"error": "drive_failed"})
        repo.session.expire_all()
        assert repo.get_drive_share(acc) is not None


class TestReadOnly:
    def test_without_account_sees_gmail_but_cannot_write(self, client, identity, repo, google):  # noqa: F811
        temp = uuid4()
        identity["result"] = BotIdentity(temp, False, None, (), False)
        share(repo, temp, "me@gmail.com")
        assert client.get("/dashboard/personal/drive").json() == {
            "writable": False,
            "unavailable": False,
            "eligible": True,
            "gmail": "me@gmail.com",
        }
        assert put(client, "x").status_code == 403
        assert client.delete("/dashboard/personal/drive", headers=HEADERS).status_code == 403
        assert google.calls == []

    def test_without_record(self, client):
        body = client.get("/dashboard/personal/drive").json()
        assert (body["writable"], body["gmail"]) == (False, None)

    def test_identity_unavailable(self, client, identity):
        identity["result"] = IdentityUnavailable()
        body = client.get("/dashboard/personal/drive").json()
        assert (body["unavailable"], body["gmail"]) == (True, None)


class TestIsolation:
    def test_only_own_share_visible(self, client, acc, repo):  # noqa: F811
        share(repo, uuid4(), "other@gmail.com")
        assert client.get("/dashboard/personal/drive").json()["gmail"] is None


class TestHttpOutsideDbExecutor:
    def test_google_runs_off_db_executor(self, client, acc, repo, google):  # noqa: F811
        share(repo, acc)
        put(client, "new")
        client.delete("/dashboard/personal/drive", headers=HEADERS)
        assert google.threads and not any(t.startswith("dashboard-db") for t in google.threads)
