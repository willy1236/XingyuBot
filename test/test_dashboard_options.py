"""伺服器管理後台 T-04：選項 API 與衝突比對。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from test_dashboard_auth import dashboard_env, make_app, make_session  # noqa: F401  (fixture 與 helper)
from test_dashboard_guilds import MANAGE_CHANNELS, MANAGE_GUILD, g, seed_token
from test_dashboard_guilds import discord as discord_env  # noqa: F401  (fixture)
from test_dashboard_notifies import (
    GUILD_ID,
    LOCKED_ROLE,
    MANAGED_ROLE,
    NO_HISTORY_CHANNEL,
    NO_SEND_CHANNEL,
    OK_CHANNEL,
    OK_ROLE,
    VOICE_CHANNEL,
    fake_bot,
    fake_guild,
)
from test_identity import repo  # noqa: F401

from starlib import sclient
from starServer.dashboard.conflict import Conflict, check_conflict


def guild_with_lists() -> SimpleNamespace:
    guild = fake_guild()
    channels = [guild.get_channel(i) for i in (OK_CHANNEL, VOICE_CHANNEL, NO_SEND_CHANNEL, NO_HISTORY_CHANNEL, 15)]
    for pos, c in enumerate(channels):
        c.position = pos
    roles = [guild.get_role(i) for i in (GUILD_ID, MANAGED_ROLE, LOCKED_ROLE, OK_ROLE)]
    for r in roles:
        r.color = SimpleNamespace(value=0xFF0000 if r.id == OK_ROLE else 0)
    guild.channels = channels
    guild.roles = roles
    return guild


class TestOptionsEndpoint:
    @pytest.fixture
    def client(self, discord_env, repo, dashboard_env, monkeypatch) -> TestClient:  # noqa: F811
        seed_token(repo, dashboard_env.credential_id)
        make_session(repo)
        discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_CHANNELS)]
        monkeypatch.setattr(sclient, "bot", fake_bot(guild_with_lists()))
        c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
        c.cookies.set("dashboard_session", "sid")
        return c

    def get(self, client: TestClient, notify_type: str):
        return client.get(f"/dashboard/guilds/{GUILD_ID}/options", params={"notify_type": notify_type})

    def test_only_valid_channels_and_roles(self, client):
        body = self.get(client, "channel:1").json()
        # 語音頻道、缺 Send Messages 的頻道不列；缺 Read Message History 的非定時通知仍可用
        assert [c["id"] for c in body["channels"]] == [str(OK_CHANNEL), str(NO_HISTORY_CHANNEL), "15"]
        assert body["channels"][0] == {"id": str(OK_CHANNEL), "name": "general", "type": "text"}
        assert body["channels"][2]["type"] == "news"
        # @everyone、managed、不可提及的身分組不列
        assert body["roles"] == [{"id": str(OK_ROLE), "name": "ping", "color": "#ff0000"}]

    def test_scheduled_type_requires_read_history(self, client):
        body = self.get(client, "channel:4").json()  # WeatherForecast
        assert str(NO_HISTORY_CHANNEL) not in [c["id"] for c in body["channels"]]

    def test_community_type(self, client):
        assert self.get(client, "community:1").status_code == 200

    @pytest.mark.parametrize("bad", ["channel:9", "channel:99", "4", "community:6", ""])
    def test_invalid_type(self, client, bad):
        res = self.get(client, bad)
        assert (res.status_code, res.json()) == (400, {"error": "invalid_request"})

    def test_missing_type(self, client):
        assert client.get(f"/dashboard/guilds/{GUILD_ID}/options").status_code == 400

    def test_no_permission(self, client, discord_env):
        discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_GUILD)]
        res = self.get(client, "channel:1")
        assert (res.status_code, res.json()) == (403, {"error": "no_permission"})

    def test_bot_not_in_guild(self, client, monkeypatch):
        monkeypatch.setattr(sclient, "bot", fake_bot(None))
        res = self.get(client, "channel:1")
        assert (res.status_code, res.json()) == (404, {"error": "bot_not_in_guild"})


class TestCheckConflict:
    def test_same_values_ok(self):
        assert check_conflict({"channel_id": 5, "role_id": None}, {"channel_id": "5", "role_id": None}) is None

    def test_changed_value(self):
        c = check_conflict({"channel_id": 6, "role_id": 7}, {"channel_id": "5", "role_id": "7"})
        assert c == Conflict({"channel_id": "6", "role_id": "7"}) and not c.deleted

    def test_role_removed_or_added(self):
        assert check_conflict({"role_id": None}, {"role_id": "7"}) is not None
        assert check_conflict({"role_id": 7}, {"role_id": None}) is not None

    def test_deleted(self):
        c = check_conflict(None, {"channel_id": "5"})
        assert c is not None and c.deleted and c.current is None

    def test_only_compares_fields_in_original(self):
        # 表上沒打勾的欄位（original 沒有）在資料庫變動不算衝突
        assert check_conflict({"channel_id": 5, "message": "changed"}, {"channel_id": "5"}) is None

    def test_to_error(self):
        e = Conflict({"channel_id": "6"}).to_error()
        assert (e.status, e.code, e.extra) == (409, "conflict", {"deleted": False, "current": {"channel_id": "6"}})
        e = Conflict(None).to_error()
        assert e.extra == {"deleted": True, "current": None}
