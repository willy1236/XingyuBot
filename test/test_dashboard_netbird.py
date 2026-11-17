"""個人區 NetBird：節點查詢與按下才產生的安裝指令（假 NetBird API、假 auth server，真實 PostgreSQL）。"""

from __future__ import annotations

import threading
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_dashboard_auth import FRONTEND, USER_ID, dashboard_env, make_app, make_session  # noqa: F401
from test_dashboard_domalyze_login import OTHER_ID, FakeBot, account
from test_dashboard_personal import directory, identity  # noqa: F401
from test_identity import repo  # noqa: F401

from starlib import netbird_setup, sclient
from starlib.database import NetBirdBinding
from starlib.exceptions import APINetworkError
from starlib.identity import BotIdentity
from starServer.dashboard import personal

OWN = int(USER_ID)
HEADERS = {"Origin": FRONTEND}


class FakeNetBird:
    """記錄呼叫的 NetBirdAPI 替身，不連正式 API。"""

    down = False
    groups: dict[str, dict] = {}
    peers: dict[str, list[dict]] = {}
    calls: list[str] = []
    threads: set[str] = set()

    def __init__(self):
        pass

    @classmethod
    def reset(cls):
        cls.down, cls.groups, cls.peers, cls.calls, cls.threads = False, {}, {}, [], set()

    def _check(self, name):
        type(self).calls.append(name)
        type(self).threads.add(threading.current_thread().name)
        if self.down:
            raise APINetworkError("down")

    def get_group(self, group_id):
        self._check("get_group")
        return next((g for g in self.groups.values() if g["id"] == group_id), None)

    def find_group_by_name(self, name):
        self._check("find_group_by_name")
        return self.groups.get(name)

    def create_group(self, name):
        self._check("create_group")
        group = {"id": f"g-{name}", "name": name, "peers": []}
        self.groups[name] = group
        return group

    def create_setup_key(self, name, auto_groups, expires_in=86400, usage_limit=1):
        self._check("create_setup_key")
        return {"id": "key-id", "key": "SECRET-KEY"}

    def get_peers_in_group(self, group_id):
        self._check("get_peers_in_group")
        return self.peers.get(group_id, [])


@pytest.fixture
def netbird(monkeypatch, repo):  # noqa: F811
    FakeNetBird.reset()
    monkeypatch.setattr(netbird_setup, "NetBirdAPI", FakeNetBird)
    monkeypatch.setattr(netbird_setup, "sqldb", repo)
    return FakeNetBird


@pytest.fixture
def client(repo, identity, netbird, monkeypatch) -> TestClient:  # noqa: F811
    monkeypatch.setattr(personal, "sqldb", repo)
    monkeypatch.setattr(sclient, "bot", FakeBot({OWN: ("Some One", None)}))
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
    make_session(repo)
    c.cookies.set("dashboard_session", "sid")
    return c


def bind(repo, user_id, group_id="g1"):  # noqa: F811
    repo.session.merge(NetBirdBinding(user_id=user_id, group_id=group_id, group_name="user-x", last_setup_key_id="k"))
    repo.session.commit()


PEER = {"name": "pc", "ip": "100.1.1.1", "connected": True, "last_seen": "2026-11-17T01:02:03Z", "os": "Windows", "version": "0.30"}


class TestGet:
    def test_bound_with_peers_does_not_create_key(self, client, directory, repo, netbird):  # noqa: F811
        acc = uuid4()
        directory.accounts[OWN] = account(acc)
        bind(repo, acc)
        netbird.peers["g1"] = [PEER]
        body = client.get("/dashboard/personal/netbird").json()
        assert body == {"writable": True, "unavailable": False, "bound": True, "peers": [PEER]}
        assert "create_setup_key" not in netbird.calls and "create_group" not in netbird.calls

    def test_bound_without_peers(self, client, directory, repo):  # noqa: F811
        acc = uuid4()
        directory.accounts[OWN] = account(acc)
        bind(repo, acc)
        body = client.get("/dashboard/personal/netbird").json()
        assert (body["bound"], body["peers"]) == (True, [])

    def test_not_bound(self, client, directory, netbird):
        directory.accounts[OWN] = account(uuid4())
        body = client.get("/dashboard/personal/netbird").json()
        assert (body["bound"], body["writable"]) == (False, True)
        assert netbird.calls == []

    def test_without_account_read_only(self, client, identity, repo, netbird):  # noqa: F811
        temp = uuid4()
        identity["result"] = BotIdentity(temp, False, None, (), False)
        bind(repo, temp)
        netbird.peers["g1"] = [PEER]
        body = client.get("/dashboard/personal/netbird").json()
        assert body == {"writable": False, "unavailable": False, "bound": True, "peers": [PEER]}

    def test_without_account_nor_record(self, client):
        body = client.get("/dashboard/personal/netbird").json()
        assert (body["bound"], body["writable"], body["unavailable"]) == (False, False, False)

    def test_identity_unavailable(self, client, identity):
        from starlib.identity import IdentityUnavailable

        identity["result"] = IdentityUnavailable()
        body = client.get("/dashboard/personal/netbird").json()
        assert (body["unavailable"], body["bound"]) == (True, False)

    def test_api_down(self, client, directory, repo, netbird):  # noqa: F811
        acc = uuid4()
        directory.accounts[OWN] = account(acc)
        bind(repo, acc)
        netbird.down = True
        res = client.get("/dashboard/personal/netbird")
        assert (res.status_code, res.json()) == (502, {"error": "netbird_unavailable"})


class TestHttpOutsideDbExecutor:
    """NetBird 的 HTTP 等待不能佔著 dashboard 專屬的 DB executor。"""

    def test_get_and_setup(self, client, directory, repo, netbird):  # noqa: F811
        acc = uuid4()
        directory.accounts[OWN] = account(acc)
        bind(repo, acc)
        client.get("/dashboard/personal/netbird")
        client.post("/dashboard/personal/netbird/setup", headers=HEADERS)
        assert netbird.threads and not any(t.startswith("dashboard-db") for t in netbird.threads)


class TestSetup:
    def test_creates_binding_on_account_id(self, client, directory, repo, netbird):  # noqa: F811
        acc = uuid4()
        directory.accounts[OWN] = account(acc)
        res = client.post("/dashboard/personal/netbird/setup", headers=HEADERS)
        body = res.json()
        assert body["command"] == "netbird up --setup-key SECRET-KEY"
        assert "netbird up --setup-key SECRET-KEY" in body["bat"] and body["bat"].startswith("@echo off\r\n")
        binding = repo.get_netbird_binding(acc)
        assert (binding.group_id, binding.group_name, binding.last_setup_key_id) == (f"g-user-{acc}", f"user-{acc}", "key-id")
        # 綁定後 GET 看得到
        assert client.get("/dashboard/personal/netbird").json()["bound"] is True

    def test_reuses_existing_group(self, client, directory, repo, netbird):  # noqa: F811
        acc = uuid4()
        directory.accounts[OWN] = account(acc)
        netbird.groups[f"user-{acc}"] = {"id": "g1", "name": f"user-{acc}", "peers": []}
        bind(repo, acc, "g1")
        client.post("/dashboard/personal/netbird/setup", headers=HEADERS)
        assert "create_group" not in netbird.calls
        assert repo.get_netbird_binding(acc).last_setup_key_id == "key-id"

    def test_requires_account(self, client, netbird):
        res = client.post("/dashboard/personal/netbird/setup", headers=HEADERS)
        assert (res.status_code, res.json()) == (403, {"error": "domalyze_required"})
        assert netbird.calls == []

    def test_api_down_leaves_no_binding(self, client, directory, repo, netbird):  # noqa: F811
        acc = uuid4()
        directory.accounts[OWN] = account(acc)
        netbird.down = True
        res = client.post("/dashboard/personal/netbird/setup", headers=HEADERS)
        assert (res.status_code, res.json()) == (502, {"error": "netbird_unavailable"})
        assert repo.get_netbird_binding(acc) is None

    def test_rejects_bad_origin(self, client, directory):
        directory.accounts[OWN] = account(uuid4())
        res = client.post("/dashboard/personal/netbird/setup", headers={"Origin": "https://evil.example"})
        assert res.status_code == 400
