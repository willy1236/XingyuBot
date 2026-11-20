"""bot owner 的營運入口（W-12）：頻道清單、停權與解除停權、修改紀錄、/dashboard/me 的 is_bot_owner（真實 PostgreSQL，測完 rollback）。"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from starlib import sclient, twitch_audit
from starlib.database import APIType, OAuthToken, TwitchBotJoinChannel
from starlib.identity.client import LinkedPassport, ResolvedAccount
from starlib.messaging import cache_invalidation
from starlib.messaging.rpc import RpcHandlerError
from starlib.twitch_audit import AuditActor, list_changes
from starlib.twitch_tokens import BROADCASTER_CLIENT_SEQ, ENABLE_SCOPES
from starServer.dashboard import channel_activation, channels, ops, twitch_control
from starServer.dashboard.channel_health import ChannelHealth
from tests.helpers.dashboard_auth import (
    FRONTEND,
    USER_ID,
    make_app,
    make_domalyze_session,
    make_session,
    make_twitch_session,
)
from tests.helpers.identity import _account

pytestmark = pytest.mark.usefixtures("dashboard_env")

CHANNEL_ID = 2000000121
OTHER_ID = 2000000122
BASE = "/dashboard/ops/channels"
NOW = datetime(2026, 1, 1, tzinfo=UTC)


class Spy:
    def __init__(self):
        self.owners: set[int] = {int(USER_ID)}
        self.sync_calls: list[int] = []
        self.sync_result: object = twitch_control.SyncResult(joined=False)
        self.invalidated: list[tuple[str, str | None]] = []
        self.health_calls: list[int] = []
        self.health = ChannelHealth("partial", ("not_mod",), ("follow_response",))


@pytest.fixture
def spy(monkeypatch, repo) -> Spy:
    spy = Spy()
    for module in (channels, channel_activation, ops, twitch_audit):
        monkeypatch.setattr(module, "sqldb", repo)

    async def is_owner(user):
        return user.id in spy.owners

    monkeypatch.setattr(sclient, "bot", SimpleNamespace(is_owner=is_owner))

    async def sync_channel(twitch_id):
        spy.sync_calls.append(twitch_id)
        if isinstance(spy.sync_result, Exception):
            raise spy.sync_result
        return spy.sync_result

    monkeypatch.setattr(twitch_control, "sync_channel", sync_channel)
    monkeypatch.setattr(
        cache_invalidation, "invalidate", lambda cache, key=None, **_: spy.invalidated.append((cache, key))
    )

    async def channel_health(twitch_id: int) -> ChannelHealth:
        spy.health_calls.append(twitch_id)
        return spy.health

    monkeypatch.setattr(ops, "channel_health", channel_health)
    return spy


@pytest.fixture(autouse=True)
def _clean_channels(repo):
    # 本機 DB 可能留有手動測試的頻道列；在外層交易內清掉，測完隨 rollback 還原
    repo.session.query(TwitchBotJoinChannel).delete()
    repo.session.flush()


def client_for(session_id: str) -> TestClient:
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
    c.cookies.set("dashboard_session", session_id)
    c.headers["Origin"] = FRONTEND
    return c


@pytest.fixture
def owner(repo, spy) -> TestClient:
    return client_for(make_session(repo))


def add_channel(repo, twitch_id=CHANNEL_ID, state="enabled", banned_at=None, **kwargs) -> None:
    repo.add(TwitchBotJoinChannel(twitch_id=twitch_id, state=state, banned_at=banned_at, **kwargs))


ENDPOINTS = [
    ("get", BASE),
    ("get", f"{BASE}/{CHANNEL_ID}/health"),
    ("post", f"{BASE}/{CHANNEL_ID}/ban"),
    ("post", f"{BASE}/{CHANNEL_ID}/unban"),
    ("get", f"{BASE}/{CHANNEL_ID}/audit"),
]


class TestBotOwnerOnly:
    @pytest.mark.parametrize(("method", "path"), ENDPOINTS)
    def test_discord_non_owner_is_forbidden(self, repo, spy, method, path):
        spy.owners.clear()
        add_channel(repo)
        r = getattr(client_for(make_session(repo)), method)(path)
        assert (r.status_code, r.json()["error"]) == (403, "not_bot_owner")

    @pytest.mark.parametrize(("method", "path"), ENDPOINTS)
    def test_twitch_session_is_forbidden(self, repo, spy, method, path):
        r = getattr(client_for(make_twitch_session(repo)), method)(path)
        assert (r.status_code, r.json()["error"]) == (403, "not_bot_owner")

    @staticmethod
    def domalyze_session(repo, dashboard_env, discord: bool) -> str:
        """析域登入要經過帳號跟隨：假 auth server 要有這個帳號，session 才不會被當成已撤銷。"""
        account = replace(_account(), discord_passports=(LinkedPassport(USER_ID, "willy"),) if discord else ())
        dashboard_env.directory.by_account_id[account.account_id] = ResolvedAccount(account)
        return make_domalyze_session(repo, account.account_id, user_id=USER_ID if discord else None)

    def test_domalyze_session_without_discord_is_forbidden(self, repo, spy, dashboard_env):
        r = client_for(self.domalyze_session(repo, dashboard_env, discord=False)).get(BASE)
        assert (r.status_code, r.json()["error"]) == (403, "not_bot_owner")

    def test_domalyze_session_with_owner_discord_passes(self, repo, spy, dashboard_env):
        assert client_for(self.domalyze_session(repo, dashboard_env, discord=True)).get(BASE).status_code == 200

    def test_no_session_is_401(self, spy):
        r = TestClient(make_app(), base_url="https://testserver").get(BASE)
        assert r.status_code == 401

    def test_non_owner_cannot_ban(self, repo, spy):
        spy.owners.clear()
        add_channel(repo)
        client_for(make_session(repo)).post(f"{BASE}/{CHANNEL_ID}/ban", json={"reason": "x"})
        row = repo.session.get(TwitchBotJoinChannel, CHANNEL_ID)
        assert row is not None and row.banned_at is None and spy.sync_calls == []


class TestMe:
    def test_owner(self, owner):
        assert owner.get("/dashboard/me").json()["is_bot_owner"] is True

    def test_not_owner(self, repo, spy):
        spy.owners.clear()
        assert client_for(make_session(repo)).get("/dashboard/me").json()["is_bot_owner"] is False

    def test_twitch_session_is_not_owner(self, repo, spy):
        assert client_for(make_twitch_session(repo)).get("/dashboard/me").json()["is_bot_owner"] is False

    def test_bot_not_ready(self, repo, spy, monkeypatch):
        monkeypatch.setattr(sclient, "bot", None)
        assert client_for(make_session(repo)).get("/dashboard/me").json()["is_bot_owner"] is False


class TestList:
    def test_lists_every_channel_with_db_state_and_banned_first_class(self, owner, repo, spy):
        add_channel(repo, 1, "inactive", login="a", display_name="A", first_seen_at=NOW)
        add_channel(repo, 2, "enabled", login="b", first_seen_at=NOW + timedelta(days=1))
        add_channel(repo, 3, "disabled", banned_at=NOW, first_seen_at=NOW + timedelta(days=2))
        add_channel(repo, 4, "disabled")

        r = owner.get(BASE)

        assert r.status_code == 200
        body = r.json()
        assert (body["page"], body["page_size"], body["total"]) == (1, 50, 4)
        # 新到舊，沒有 first_seen_at 的排最後
        assert [c["id"] for c in body["channels"]] == ["3", "2", "1", "4"]
        assert [c["state"] for c in body["channels"]] == ["banned", "enabled", "inactive", "disabled"]
        assert body["channels"][2]["name"] == "A" and body["channels"][1]["name"] == "b"
        assert body["channels"][3]["name"] == "4"
        # 清單不跑完整判定
        assert spy.health_calls == []

    def test_paginates_by_50(self, owner, repo):
        for i in range(55):
            add_channel(repo, 100 + i, first_seen_at=NOW + timedelta(minutes=i))

        first = owner.get(BASE).json()
        second = owner.get(BASE, params={"page": 2}).json()

        assert (len(first["channels"]), len(second["channels"]), first["total"]) == (50, 5, 55)
        assert first["channels"][0]["id"] == "154" and second["channels"][-1]["id"] == "100"

    @pytest.mark.parametrize("page", [0, -3])
    def test_invalid_page_counts_as_first(self, owner, repo, page):
        add_channel(repo)
        body = owner.get(BASE, params={"page": page}).json()
        assert body["page"] == 1 and len(body["channels"]) == 1

    def test_channel_after_delete_data_is_still_listed(self, owner, repo):
        add_channel(repo, state="inactive", login="host")
        assert [c["id"] for c in owner.get(BASE).json()["channels"]] == [str(CHANNEL_ID)]


def add_token(repo, twitch_id, *, scope=ENABLE_SCOPES, refresh="refresh", refresh_failed_at=None, expired=False):
    credential_id = repo.get_oauth_client(APIType.Twitch, BROADCASTER_CLIENT_SEQ).credential_id
    repo.merge(
        OAuthToken(
            user_id=str(twitch_id),
            client_credential_id=credential_id,
            access_token="access",
            refresh_token=refresh,
            scope=list(scope),
            expires_at=NOW if expired else datetime.now(UTC) + timedelta(hours=1),
            refresh_failed_at=refresh_failed_at,
        )
    )


class TestTokenStats:
    @pytest.fixture
    def channels(self, repo):
        """1 正常（access token 過期也算正常）、2 沒有 token、3 refresh token 為空、4 缺 scope、5 續期被拒，
        6 停權、7 已停用：後兩者有問題也不算。"""
        for i, state in enumerate(["enabled"] * 5 + ["disabled", "disabled"], start=1):
            add_channel(repo, i, state, banned_at=NOW if i == 6 else None, first_seen_at=NOW + timedelta(days=10 - i))
        add_token(repo, 1, expired=True)
        add_token(repo, 3, refresh="")
        add_token(repo, 4, scope=[s for s in ENABLE_SCOPES if s not in ("moderation:read", "channel:read:predictions")])
        add_token(repo, 5, refresh_failed_at=NOW)
        add_token(repo, 7, scope=[])

    def test_counts_problems_of_enabled_channels_only(self, owner, channels):
        body = owner.get(BASE).json()

        assert body["token_problems"] == {"missing": 2, "scope_missing": 1, "revoked": 1}
        assert body["enabled_count"] == 5
        assert body["total"] == 7

    def test_enabled_rows_carry_token_state_and_others_do_not(self, owner, channels):
        rows = {c["id"]: c for c in owner.get(BASE).json()["channels"]}

        assert rows["1"]["token"] == {"state": "ok", "missing_scopes": []}
        assert rows["2"]["token"]["state"] == "missing"
        assert rows["3"]["token"]["state"] == "missing"
        assert rows["4"]["token"] == {
            "state": "scope_missing",
            "missing_scopes": ["moderation:read", "channel:read:predictions"],
        }
        assert rows["5"]["token"]["state"] == "revoked"
        assert "token" not in rows["6"] and "token" not in rows["7"]

    def test_filter_lists_only_problem_channels_in_list_order(self, owner, channels):
        body = owner.get(BASE, params={"token_problem": 1}).json()

        assert [c["id"] for c in body["channels"]] == ["2", "3", "4", "5"]
        assert body["total"] == 4
        assert body["token_problems"] == {"missing": 2, "scope_missing": 1, "revoked": 1}

    def test_filter_paginates_by_50(self, owner, repo):
        for i in range(55):
            add_channel(repo, 100 + i, first_seen_at=NOW + timedelta(minutes=i))
        add_token(repo, 154)

        first = owner.get(BASE, params={"token_problem": 1}).json()
        second = owner.get(BASE, params={"token_problem": 1, "page": 2}).json()

        assert (len(first["channels"]), len(second["channels"]), first["total"]) == (50, 4, 54)
        assert first["channels"][0]["id"] == "153" and second["channels"][-1]["id"] == "100"

    def test_does_not_call_twitch(self, owner, channels, spy, monkeypatch):
        from starlib import twitch_tokens

        def fail(*args, **kwargs):
            raise AssertionError("統計不該對 Twitch 發請求")

        monkeypatch.setattr(twitch_tokens.httpx, "post", fail)
        assert owner.get(BASE, params={"token_problem": 1}).status_code == 200
        assert spy.health_calls == []


class TestHealth:
    def test_returns_channel_health(self, owner, repo, spy):
        add_channel(repo)
        r = owner.get(f"{BASE}/{CHANNEL_ID}/health")
        assert r.json() == {"state": "partial", "issues": ["not_mod"], "paused_features": ["follow_response"]}
        assert spy.health_calls == [CHANNEL_ID]

    def test_unknown_channel_is_404(self, owner):
        r = owner.get(f"{BASE}/{CHANNEL_ID}/health")
        assert (r.status_code, r.json()["error"]) == (404, "channel_not_found")


class TestBan:
    @pytest.mark.parametrize("state", ["inactive", "enabled", "disabled"])
    def test_bans_any_state_and_syncs_bot(self, owner, repo, spy, state):
        add_channel(repo, state=state)

        r = owner.post(f"{BASE}/{CHANNEL_ID}/ban", json={"reason": "  濫用  "})

        assert r.status_code == 200
        body = r.json()
        assert body["bot_offline"] is False
        assert (body["channel"]["state"], body["channel"]["banned_reason"]) == ("banned", "濫用")
        row = repo.session.get(TwitchBotJoinChannel, CHANNEL_ID)
        repo.session.refresh(row)
        assert row.banned_at is not None and row.state == "disabled" and row.banned_reason == "濫用"
        assert spy.sync_calls == [CHANNEL_ID]
        assert ("twitch_channel", str(CHANNEL_ID)) in spy.invalidated or (
            "twitch_channel",
            CHANNEL_ID,
        ) in spy.invalidated

    def test_blank_reason_is_stored_as_null(self, owner, repo):
        add_channel(repo)
        owner.post(f"{BASE}/{CHANNEL_ID}/ban", json={"reason": "   "})
        row = repo.session.get(TwitchBotJoinChannel, CHANNEL_ID)
        assert row.banned_at is not None and row.banned_reason is None

    def test_reason_too_long_is_rejected(self, owner, repo, spy):
        add_channel(repo)
        r = owner.post(f"{BASE}/{CHANNEL_ID}/ban", json={"reason": "x" * 501})
        assert r.status_code == 400
        assert repo.session.get(TwitchBotJoinChannel, CHANNEL_ID).banned_at is None

    def test_unknown_channel_is_404(self, owner, spy):
        r = owner.post(f"{BASE}/{CHANNEL_ID}/ban", json={"reason": "x"})
        assert (r.status_code, r.json()["error"]) == (404, "channel_not_found")
        assert spy.sync_calls == []

    def test_records_audit_in_same_transaction(self, owner, repo):
        add_channel(repo, state="enabled")
        owner.post(f"{BASE}/{CHANNEL_ID}/ban", json={"reason": "濫用"})

        (entry,) = list_changes(CHANNEL_ID)
        assert entry.actor == AuditActor("discord", USER_ID, "Some One")
        assert (entry.source, entry.target_kind, entry.target_key, entry.action) == (
            "dashboard",
            "channel",
            "ban",
            "update",
        )
        assert entry.before == {"banned_at": None, "banned_reason": None, "state": "enabled"}
        assert entry.after is not None and entry.after["banned_reason"] == "濫用" and entry.after["state"] == "disabled"

    def test_ban_again_with_same_reason_changes_nothing(self, owner, repo, spy):
        add_channel(repo)
        owner.post(f"{BASE}/{CHANNEL_ID}/ban", json={"reason": "濫用"})
        first = repo.session.get(TwitchBotJoinChannel, CHANNEL_ID).banned_at

        owner.post(f"{BASE}/{CHANNEL_ID}/ban", json={"reason": "濫用"})

        assert repo.session.get(TwitchBotJoinChannel, CHANNEL_ID).banned_at == first
        assert len(list_changes(CHANNEL_ID)) == 1

    def test_ban_again_updates_reason_and_keeps_time(self, owner, repo):
        add_channel(repo)
        owner.post(f"{BASE}/{CHANNEL_ID}/ban", json={"reason": "a"})
        first = repo.session.get(TwitchBotJoinChannel, CHANNEL_ID).banned_at

        owner.post(f"{BASE}/{CHANNEL_ID}/ban", json={"reason": "b"})

        row = repo.session.get(TwitchBotJoinChannel, CHANNEL_ID)
        assert (row.banned_at, row.banned_reason) == (first, "b")
        assert len(list_changes(CHANNEL_ID)) == 2

    def test_bot_offline_still_bans(self, owner, repo, spy):
        spy.sync_result = twitch_control.BotOffline()
        add_channel(repo)
        r = owner.post(f"{BASE}/{CHANNEL_ID}/ban", json={"reason": "x"})
        assert r.json()["bot_offline"] is True
        assert repo.session.get(TwitchBotJoinChannel, CHANNEL_ID).banned_at is not None

    def test_bot_internal_error_is_reported_as_offline(self, owner, repo, spy):
        spy.sync_result = RpcHandlerError("boom")
        add_channel(repo)
        r = owner.post(f"{BASE}/{CHANNEL_ID}/ban", json={"reason": "x"})
        assert r.status_code == 200 and r.json()["bot_offline"] is True


class TestUnban:
    def test_returns_to_disabled_without_enabling(self, owner, repo, spy):
        add_channel(repo, state="disabled", banned_at=NOW, banned_reason="濫用")

        r = owner.post(f"{BASE}/{CHANNEL_ID}/unban")

        assert r.status_code == 200
        assert r.json()["channel"]["state"] == "disabled"
        row = repo.session.get(TwitchBotJoinChannel, CHANNEL_ID)
        repo.session.refresh(row)
        assert (row.banned_at, row.banned_reason, row.state) == (None, None, "disabled")
        assert spy.sync_calls == []

    def test_state_inactive_after_delete_data_still_returns_to_disabled(self, owner, repo):
        add_channel(repo, state="inactive", banned_at=NOW)
        owner.post(f"{BASE}/{CHANNEL_ID}/unban")
        repo.session.expire_all()
        assert repo.session.get(TwitchBotJoinChannel, CHANNEL_ID).state == "disabled"

    def test_not_banned_is_409_and_keeps_state(self, owner, repo):
        add_channel(repo, state="enabled")
        r = owner.post(f"{BASE}/{CHANNEL_ID}/unban")
        assert (r.status_code, r.json()["error"]) == (409, "channel_not_banned")
        assert repo.session.get(TwitchBotJoinChannel, CHANNEL_ID).state == "enabled"

    def test_unknown_channel_is_404(self, owner):
        r = owner.post(f"{BASE}/{CHANNEL_ID}/unban")
        assert (r.status_code, r.json()["error"]) == (404, "channel_not_found")

    def test_records_audit(self, owner, repo):
        add_channel(repo, state="disabled", banned_at=NOW, banned_reason="濫用")
        owner.post(f"{BASE}/{CHANNEL_ID}/unban")
        (entry,) = list_changes(CHANNEL_ID)
        assert (entry.target_kind, entry.target_key, entry.action) == ("channel", "unban", "update")
        assert entry.before is not None and entry.before["banned_reason"] == "濫用"
        assert entry.after == {"banned_at": None, "banned_reason": None, "state": "disabled"}


class TestAudit:
    def record(self, n: int, twitch_id=CHANNEL_ID):
        actor = AuditActor("twitch", "1", "Host")
        for i in range(n):
            twitch_audit.record_change(twitch_id, actor, "chat", "command", f"c{i}", "create", None, {"i": i})

    def test_lists_entries_newest_first_with_all_fields(self, owner, repo):
        add_channel(repo)
        self.record(2)
        self.record(1, OTHER_ID)

        r = owner.get(f"{BASE}/{CHANNEL_ID}/audit")

        assert r.status_code == 200
        body = r.json()
        assert (body["page"], body["has_next"], body["channel"]["id"]) == (1, False, str(CHANNEL_ID))
        assert [e["target_key"] for e in body["entries"]] == ["c1", "c0"]
        first = body["entries"][0]
        assert first["actor"] == {"platform": "twitch", "id": "1", "name": "Host"}
        assert (first["source"], first["target_kind"], first["action"]) == ("chat", "command", "create")
        assert (first["before"], first["after"]) == (None, {"i": 1})
        assert first["at"]

    def test_paginates_by_50(self, owner, repo):
        add_channel(repo)
        self.record(51)
        first = owner.get(f"{BASE}/{CHANNEL_ID}/audit").json()
        second = owner.get(f"{BASE}/{CHANNEL_ID}/audit", params={"page": 2}).json()
        assert (len(first["entries"]), first["has_next"]) == (50, True)
        assert (len(second["entries"]), second["has_next"]) == (1, False)

    def test_unknown_channel_is_404(self, owner):
        r = owner.get(f"{BASE}/{CHANNEL_ID}/audit")
        assert (r.status_code, r.json()["error"]) == (404, "channel_not_found")
