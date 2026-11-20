"""頻道後台的修改紀錄（M-02）：實況主與 mod 都看得到整份紀錄，不回操作者的 ID（真實 PostgreSQL，假 Helix）。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from starlib import twitch_audit, twitch_commands
from starlib.database import TwitchBotJoinChannel
from starlib.messaging import cache_invalidation
from starlib.twitch_audit import AuditActor
from starServer.dashboard import channel_audit, channel_settings, channels, ops
from tests.helpers.dashboard_auth import FRONTEND, make_app, make_session, make_twitch_session

pytestmark = pytest.mark.usefixtures("dashboard_env")

HEADERS = {"Origin": FRONTEND}
B = 2000000701  # 頻道
A = "2000000711"  # mod
URL = f"/dashboard/channels/{B}"
HOST = AuditActor("twitch", str(B), "Bravo")


@pytest.fixture(autouse=True)
def _env(monkeypatch, repo):
    for module in (channels, channel_audit, channel_settings, ops, twitch_audit, twitch_commands):
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


def record(repo, actor=HOST, source="dashboard", kind="command", key="hi", action="create") -> None:
    twitch_audit.record_change(B, actor, source, kind, key, action, None, {"response": "hello"})
    repo.session.flush()


class TestAuditLog:
    def test_mod_change_is_visible_to_host_without_actor_id(self, repo, host):
        # mod 寫入時記成 Twitch 帳號由 test_channel_mod_access 驗；這裡驗紀錄端點怎麼回
        record(repo, actor=AuditActor("twitch", A, "Ann"))

        body = host.get(f"{URL}/audit").json()

        entry = body["entries"][0]
        assert entry["actor"] == {"platform": "twitch", "name": "Ann"}
        assert set(entry) == {"id", "at", "actor", "source", "target_kind", "target_key", "action", "before", "after"}
        assert (entry["source"], entry["target_kind"], entry["after"]) == (
            "dashboard",
            "command",
            {"response": "hello"},
        )

    def test_mod_sees_host_changes_and_chat_source(self, repo, mod):
        record(repo, kind="timer", key="1")
        record(repo, actor=AuditActor("twitch", "100", "Viewer"), source="chat")

        entries = mod.get(f"{URL}/audit").json()["entries"]

        assert [(e["source"], e["target_kind"], e["actor"]["name"]) for e in entries] == [
            ("chat", "command", "Viewer"),
            ("dashboard", "timer", "Bravo"),
        ]

    def test_includes_old_discord_actor_and_forward_and_ban_entries(self, repo, host):
        record(repo, actor=AuditActor("discord", "111", "Some One"), kind="forward", key="discord")
        record(repo, actor=AuditActor("discord", "222", "Owner"), kind="channel", key="ban", action="update")

        entries = host.get(f"{URL}/audit").json()["entries"]

        assert [(e["actor"]["platform"], e["target_kind"]) for e in entries] == [
            ("discord", "channel"),
            ("discord", "forward"),
        ]

    def test_pages_by_50(self, repo, host):
        for i in range(51):
            record(repo, key=f"c{i}")

        first = host.get(f"{URL}/audit").json()
        second = host.get(f"{URL}/audit?page=2").json()

        assert (len(first["entries"]), first["page"], first["has_next"]) == (50, 1, True)
        assert (len(second["entries"]), second["page"], second["has_next"]) == (1, 2, False)

    def test_empty(self, host):
        assert host.get(f"{URL}/audit").json() == {"entries": [], "page": 1, "has_next": False}

    @pytest.mark.parametrize("who", ["other_twitch", "discord"])
    def test_not_manageable_is_forbidden(self, repo, who):
        sid = make_twitch_session(repo, twitch_id="777") if who == "other_twitch" else make_session(repo)

        r = client_for(sid).get(f"{URL}/audit")

        assert r.status_code == 403 and r.json() == {"error": "channel_forbidden"}
