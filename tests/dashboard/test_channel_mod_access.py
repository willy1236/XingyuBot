"""頻道 mod 進入頻道後台（M-01）：頻道清單與個人區、角色、mod 可寫的區塊、owner 限定的端點與修改紀錄的操作者（真實 PostgreSQL，假 Helix）。"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from starlib import twitch_audit, twitch_commands, twitch_event_responses, twitch_timers
from starlib.database import TwitchBotJoinChannel
from starlib.identity import LinkedPassport, ResolvedAccount
from starlib.messaging import cache_invalidation
from starlib.twitch_audit import list_changes
from starServer.dashboard import channel_forward, channel_settings, channels, twitch_control
from starServer.dashboard.channel_health import ChannelHealth
from tests.helpers.accounts import account
from tests.helpers.dashboard_auth import (
    BOT_TWITCH_ID,
    FRONTEND,
    USER_ID,
    make_app,
    make_domalyze_session,
    make_session,
    make_twitch_session,
)

pytestmark = pytest.mark.usefixtures("dashboard_env")

HEADERS = {"Origin": FRONTEND}
A, A2 = "2000000501", "2000000502"  # mod 的 Twitch 帳號
B, C = 2000000601, 2000000602  # mod 協作的頻道
ALL = (int(A), int(A2), B, C, int(BOT_TWITCH_ID))


@pytest.fixture(autouse=True)
def _env(monkeypatch, repo):
    for module in (
        channels,
        channel_forward,
        channel_settings,
        twitch_commands,
        twitch_timers,
        twitch_event_responses,
        twitch_audit,
    ):
        monkeypatch.setattr(module, "sqldb", repo)
    repo.session.query(TwitchBotJoinChannel).filter(
        TwitchBotJoinChannel.twitch_id.in_(ALL)  # pyright: ignore[reportAttributeAccessIssue]
    ).delete()
    repo.session.flush()
    repo.add(TwitchBotJoinChannel(twitch_id=B, state="enabled", login="bravo", display_name="Bravo"))
    monkeypatch.setattr(cache_invalidation, "invalidate", lambda *a, **kw: None)
    monkeypatch.setattr(twitch_control, "check_template", AsyncMock(return_value="ok"))

    async def health(twitch_id: int) -> ChannelHealth:
        return ChannelHealth("partial", ("not_mod",), ("follow_response",))

    monkeypatch.setattr(channels, "channel_health", health)


@pytest.fixture
def sync(monkeypatch) -> AsyncMock:
    mock = AsyncMock(return_value=twitch_control.SyncResult(joined=False))
    monkeypatch.setattr(twitch_control, "sync_channel", mock)
    return mock


def client_for(session_id: str) -> TestClient:
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False, headers=HEADERS)
    c.cookies.set("dashboard_session", session_id)
    return c


def twitch_client(repo, twitch_id=A, name="Ann") -> TestClient:
    return client_for(make_twitch_session(repo, twitch_id=twitch_id, login=name.lower(), name=name))


def domalyze_client(repo, dashboard_env, *twitch: tuple[str, str], discord: bool = True) -> TestClient:
    acc = replace(
        account(uuid4(), discord_ids=(int(USER_ID),) if discord else ()),
        twitch_passports=tuple(LinkedPassport(i, n) for i, n in twitch),
    )
    dashboard_env.directory.by_account_id[acc.account_id] = ResolvedAccount(acc)
    return client_for(make_domalyze_session(repo, acc.account_id, user_id=USER_ID if discord else None))


def command(**kw) -> dict:
    return {
        "name": "hi",
        "response": "hello",
        "aliases": [],
        "enabled": True,
        "global_cooldown": 30,
        "user_cooldown": 0,
        "permission": "everyone",
        **kw,
    }


class TestChannelList:
    def test_own_channel_first_then_mod_channels(self, repo, twitch_mods):
        repo.add(TwitchBotJoinChannel(twitch_id=C, state="disabled", login="alpha", display_name="Alpha"))
        twitch_mods.set(B, (A, "Ann"))
        twitch_mods.set(C, (A, "Ann"))

        body = twitch_client(repo, name="Zed").get("/dashboard/channels").json()

        # 自己的頻道還沒啟用（沒有頻道列）也排第一
        assert [(c["id"], c["role"], c["state"]) for c in body["channels"]] == [
            (A, "owner", "inactive"),
            (str(C), "mod", "disabled"),
            (str(B), "mod", "enabled"),
        ]

    def test_personal_overview_lists_mod_channels(self, repo, twitch_mods):
        twitch_mods.set(B, (A, "Ann"))

        body = twitch_client(repo).get("/dashboard/personal/overview").json()

        assert [(c["id"], c["role"]) for c in body["channels"]] == [(A, "owner"), (str(B), "mod")]

    def test_domalyze_lists_mod_channels_of_every_linked_twitch(self, repo, dashboard_env, twitch_mods):
        repo.add(TwitchBotJoinChannel(twitch_id=C, state="enabled", login="alpha", display_name="Alpha"))
        twitch_mods.set(B, (A, "Ann"))
        twitch_mods.set(C, (A2, "Ann2"))

        c = domalyze_client(repo, dashboard_env, (A, "Ann"), (A2, "Ann2"))
        body = c.get("/dashboard/channels").json()

        assert [(x["id"], x["role"]) for x in body["channels"]] == [
            (A, "owner"),
            (A2, "owner"),
            (str(C), "mod"),
            (str(B), "mod"),
        ]

    def test_discord_login_has_no_mod_channels(self, repo, twitch_mods):
        twitch_mods.set(B, (USER_ID, "Some One"))

        assert client_for(make_session(repo)).get("/dashboard/channels").json() == {"channels": []}
        assert twitch_mods.calls == []

    def test_inactive_channel_is_not_listed(self, repo, twitch_mods):
        repo.add(TwitchBotJoinChannel(twitch_id=C, state="inactive", display_name="Alpha"))
        twitch_mods.set(C, (A, "Ann"))

        ids = [c["id"] for c in twitch_client(repo).get("/dashboard/channels").json()["channels"]]

        assert ids == [A]

    def test_banned_channel_is_listed_and_opens_as_banned(self, repo, twitch_mods):
        repo.add(
            TwitchBotJoinChannel(
                twitch_id=C, state="disabled", display_name="Alpha", banned_at=datetime(2026, 1, 1, tzinfo=UTC)
            )
        )
        twitch_mods.set(C, (A, "Ann"))
        c = twitch_client(repo)

        listed = {x["id"]: x["state"] for x in c.get("/dashboard/channels").json()["channels"]}
        detail = c.get(f"/dashboard/channels/{C}")

        assert listed[str(C)] == "banned"
        assert detail.status_code == 200 and detail.json()["state"] == "banned"

    def test_bot_account_has_no_mod_channels(self, repo, twitch_mods):
        twitch_mods.set(B, (BOT_TWITCH_ID, "xingyu"))

        body = twitch_client(repo, twitch_id=BOT_TWITCH_ID, name="xingyu").get("/dashboard/channels").json()

        assert [c["role"] for c in body["channels"]] == ["owner"]


class TestModAccess:
    def test_channel_detail_has_mod_role_and_status(self, repo, twitch_mods):
        twitch_mods.set(B, (A, "Ann"))

        body = twitch_client(repo).get(f"/dashboard/channels/{B}").json()

        assert (body["role"], body["forward_access"], body["state"]) == ("mod", "mod", "enabled")
        assert body["health"]["paused_features"] == ["follow_response"]

    def test_owner_detail_keeps_owner_role(self, repo):
        body = twitch_client(repo).get(f"/dashboard/channels/{A}").json()

        assert (body["role"], body["forward_access"]) == ("owner", "need_domalyze")

    def test_not_a_mod_is_forbidden(self, repo, twitch_mods):
        r = twitch_client(repo).get(f"/dashboard/channels/{B}")

        assert r.status_code == 403 and r.json() == {"error": "channel_forbidden"}

    def test_mod_writes_commands_and_is_recorded_as_twitch_account(self, repo, twitch_mods):
        twitch_mods.set(B, (A, "Ann"))

        r = twitch_client(repo).post(f"/dashboard/channels/{B}/commands", json=command())

        assert r.status_code == 200
        (entry,) = list_changes(B)
        assert (entry.actor.platform, entry.actor.id, entry.actor.name) == ("twitch", A, "Ann")

    def test_mod_writes_timers(self, repo, twitch_mods):
        twitch_mods.set(B, (A, "Ann"))

        r = twitch_client(repo).post(f"/dashboard/channels/{B}/timers", json={"message": "hi", "interval_minutes": 10})

        assert r.status_code == 200
        assert list_changes(B)[0].actor.id == A

    def test_mod_writes_event_responses(self, repo, twitch_mods):
        twitch_mods.set(B, (A, "Ann"))

        default = {"enabled": False, "template": twitch_event_responses.DEFAULTS["follow"]}
        r = twitch_client(repo).put(
            f"/dashboard/channels/{B}/event-responses/follow",
            json={"values": {"enabled": True, "template": "歡迎 {user}"}, "original": default},
        )

        assert r.status_code == 200, r.json()
        assert list_changes(B)[0].actor.id == A

    def test_domalyze_mod_is_recorded_as_smallest_linked_mod_account(self, repo, dashboard_env, twitch_mods):
        twitch_mods.set(B, (A2, "Ann2"), (A, "Ann"))

        c = domalyze_client(repo, dashboard_env, (A2, "Ann2"), (A, "Ann"))
        assert c.post(f"/dashboard/channels/{B}/commands", json=command()).status_code == 200

        assert (list_changes(B)[0].actor.platform, list_changes(B)[0].actor.id) == ("twitch", A)

    def test_domalyze_owner_is_recorded_as_channel_twitch_account(self, repo, dashboard_env):
        c = domalyze_client(repo, dashboard_env, (str(B), "Bravo"))

        assert c.post(f"/dashboard/channels/{B}/commands", json=command()).status_code == 200

        entry = list_changes(B)[0]
        assert (entry.actor.platform, entry.actor.id, entry.actor.name) == ("twitch", str(B), "Bravo")

    def test_removed_mod_is_blocked_after_cache_expiry(self, repo, twitch_mods, monkeypatch):
        twitch_mods.set(B, (A, "Ann"))
        c = twitch_client(repo)
        assert c.get(f"/dashboard/channels/{B}").status_code == 200

        twitch_mods.set(B)
        monkeypatch.setattr(channels.channel_mods, "_cache", {})  # 等同 60 秒過去

        r = c.post(f"/dashboard/channels/{B}/commands", json=command())
        assert r.status_code == 403 and r.json() == {"error": "channel_forbidden"}
        assert [x["id"] for x in c.get("/dashboard/channels").json()["channels"]] == [A]


class TestOwnerOnly:
    @pytest.fixture
    def mod(self, repo, dashboard_env, twitch_mods) -> TestClient:
        twitch_mods.set(B, (A, "Ann"))
        # 析域登入且有 Discord 的 mod：轉發的 forward_access 對實況主本人會是 ok，mod 仍不能改
        return domalyze_client(repo, dashboard_env, (A, "Ann"))

    @pytest.mark.parametrize(
        ("method", "path", "body"),
        [
            ("POST", "disable", None),
            ("POST", "delete-data", {"confirm_login": "bravo"}),
            ("PUT", "forward", {"guild_id": None, "channel_id": None}),
            ("GET", "forward/options", None),
        ],
    )
    def test_rejected(self, repo, mod, sync, method, path, body):
        r = mod.request(method, f"/dashboard/channels/{B}/{path}", json=body)

        assert r.status_code == 403 and r.json() == {"error": "channel_owner_only"}
        sync.assert_not_called()
        row = repo.session.get(TwitchBotJoinChannel, B, populate_existing=True)
        assert row is not None and row.state == "enabled"
        assert list_changes(B) == []

    def test_forward_is_readable_but_not_editable(self, mod, bot_not_ready):
        r = mod.get(f"/dashboard/channels/{B}/forward")

        assert r.status_code == 200 and r.json()["editable"] is False

    def test_enable_entry_redirects_back_with_owner_only(self, repo, twitch_mods, site):
        twitch_mods.set(B, (A, "Ann"))
        site.cookies.set("dashboard_session", make_twitch_session(repo, twitch_id=A, login="ann", name="Ann"))

        response = site.get("/to/dashboard-twitch-enable", params={"channel": str(B), "origin": FRONTEND})

        location = urlparse(response.headers["location"])
        assert f"{location.scheme}://{location.netloc}{location.path}" == f"{FRONTEND}/dashboard/twitch/{B}"
        assert parse_qs(location.query)["notice"] == ["owner_only"]


@pytest.fixture
def bot_not_ready(monkeypatch):
    from starlib import sclient

    monkeypatch.setattr(sclient, "bot", None)
