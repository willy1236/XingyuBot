"""mod 協作開關（M-03）：只限實況主、每次開關記修改紀錄、關閉後 mod 的下一次操作被擋下（真實 PostgreSQL，假 Helix）。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from starlib import twitch_audit
from starlib.database import TwitchBotJoinChannel
from starlib.messaging import cache_invalidation
from starlib.twitch_audit import AuditActor, list_changes
from starServer.dashboard import channel_settings, channels, ops
from tests.helpers.dashboard_auth import FRONTEND, make_app, make_twitch_session

pytestmark = pytest.mark.usefixtures("dashboard_env")

HEADERS = {"Origin": FRONTEND}
B = 2000000801  # 頻道
A = "2000000811"  # mod
URL = f"/dashboard/channels/{B}"
HOST = AuditActor("twitch", str(B), "Bravo")


@pytest.fixture(autouse=True)
def _env(monkeypatch, repo):
    for module in (channels, channel_settings, ops, twitch_audit):
        monkeypatch.setattr(module, "sqldb", repo)
    for twitch_id in (B, int(A)):
        existing = repo.session.get(TwitchBotJoinChannel, twitch_id)
        if existing is not None:
            repo.session.delete(existing)
    repo.session.flush()
    repo.add(TwitchBotJoinChannel(twitch_id=B, state="enabled", login="bravo", display_name="Bravo"))
    invalidated: list[tuple[str, str | None]] = []
    monkeypatch.setattr(cache_invalidation, "invalidate", lambda cache, key=None, **_: invalidated.append((cache, key)))
    return invalidated


@pytest.fixture
def invalidated(_env):
    return _env


def client_for(session_id: str) -> TestClient:
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False, headers=HEADERS)
    c.cookies.set("dashboard_session", session_id)
    return c


@pytest.fixture
def host(repo) -> TestClient:
    return client_for(make_twitch_session(repo, twitch_id=str(B), session_id="host", login="bravo", name="Bravo"))


@pytest.fixture
def mod(repo, twitch_mods) -> TestClient:
    twitch_mods.set(B, (A, "Ann"))
    return client_for(make_twitch_session(repo, twitch_id=A, session_id="mod", login="ann", name="Ann"))


def test_detail_reports_switch_default_on(host, mod):
    assert host.get(URL).json()["mod_collab_enabled"] is True
    assert mod.get(URL).json()["mod_collab_enabled"] is True


def test_turning_off_records_and_blocks_mod(host, mod, invalidated):
    assert mod.get(URL).status_code == 200

    r = host.put(f"{URL}/mod-collab", json={"enabled": False})

    assert r.status_code == 200 and r.json() == {"mod_collab_enabled": False}
    (entry,) = list_changes(B)
    assert (entry.actor, entry.source, entry.target_kind, entry.target_key, entry.action) == (
        HOST,
        "dashboard",
        "mod_collab",
        "enabled",
        "update",
    )
    assert (entry.before, entry.after) == ({"enabled": True}, {"enabled": False})
    assert ("twitch_channel", str(B)) in invalidated
    # 候選頻道每次查 DB：mod 的下一次操作就被擋下，也不在清單裡
    r = mod.get(URL)
    assert r.status_code == 403 and r.json() == {"error": "channel_forbidden"}
    assert [c["id"] for c in mod.get("/dashboard/channels").json()["channels"]] == [A]
    assert host.get(URL).json()["mod_collab_enabled"] is False


def test_turning_back_on_restores_mod(host, mod):
    host.put(f"{URL}/mod-collab", json={"enabled": False})

    host.put(f"{URL}/mod-collab", json={"enabled": True})

    assert mod.get(URL).status_code == 200
    assert [e.after for e in list_changes(B)] == [{"enabled": True}, {"enabled": False}]


def test_same_value_writes_nothing(host, invalidated):
    r = host.put(f"{URL}/mod-collab", json={"enabled": True})

    assert r.status_code == 200
    assert list_changes(B) == []
    assert invalidated == []


def test_mod_cannot_switch(repo, mod):
    r = mod.put(f"{URL}/mod-collab", json={"enabled": False})

    assert r.status_code == 403 and r.json() == {"error": "channel_owner_only"}
    assert repo.session.get(TwitchBotJoinChannel, B, populate_existing=True).mod_collab_enabled is True
    assert list_changes(B) == []


def test_ops_does_not_show_switch(repo, host, monkeypatch):
    async def owner(info):
        return True

    monkeypatch.setattr(ops, "is_bot_owner", owner)
    host.put(f"{URL}/mod-collab", json={"enabled": False})

    channels_page = host.get("/dashboard/ops/channels").json()["channels"]
    audit = host.get(f"/dashboard/ops/channels/{B}/audit").json()

    assert all("mod_collab_enabled" not in c for c in channels_page)
    assert "mod_collab_enabled" not in audit["channel"]
    # 開關紀錄營運入口也看得到
    assert audit["entries"][0]["target_kind"] == "mod_collab"
