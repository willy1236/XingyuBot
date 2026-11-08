"""伺服器管理後台 T-06：頻道通知的新增、修改、刪除與條件式寫入。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from test_dashboard_auth import FRONTEND, dashboard_env, make_app, make_session  # noqa: F401  (fixture 與 helper)
from test_dashboard_guilds import MANAGE_CHANNELS, g, seed_token
from test_dashboard_guilds import discord as discord_env  # noqa: F401  (fixture)
from test_dashboard_notifies import (
    GUILD_ID,
    LOCKED_ROLE,
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
from starServer.dashboard import channel_notifies
from starlib.database import NotifyChannelType as T
from starlib.exceptions import DataExistError


class TestRepositoryMethods:
    def test_insert_does_not_overwrite(self, repo):
        repo.insert_notify_channel(GUILD_ID, T.AllAnnouncements, 1, 2)
        with pytest.raises(DataExistError):
            repo.insert_notify_channel(GUILD_ID, T.AllAnnouncements, 3, None)
        row = repo.get_notify_channel_fresh(GUILD_ID, T.AllAnnouncements)
        assert (row.channel_id, row.role_id) == (1, 2)

    def test_update_if_matches_null_and_value(self, repo):
        repo.add_notify_channel(GUILD_ID, T.MemberJoin, 1, None, None)
        assert repo.update_notify_channel_if(GUILD_ID, T.MemberJoin, {"channel_id": 1, "message": None}, {"channel_id": 5, "message": "hi"}) == 1
        # 原始值已不符
        assert repo.update_notify_channel_if(GUILD_ID, T.MemberJoin, {"channel_id": 1, "message": None}, {"channel_id": 6}) == 0
        row = repo.get_notify_channel_fresh(GUILD_ID, T.MemberJoin)
        assert (row.channel_id, row.message) == (5, "hi")

    def test_unlisted_columns_untouched(self, repo):
        repo.add_notify_channel(GUILD_ID, T.WeatherForecast, 1, 77, None)
        assert repo.update_notify_channel_if(GUILD_ID, T.WeatherForecast, {"channel_id": 1}, {"channel_id": 2}) == 1
        assert repo.get_notify_channel_fresh(GUILD_ID, T.WeatherForecast).role_id == 77

    def test_delete_if(self, repo):
        repo.add_notify_channel(GUILD_ID, T.JoinLog, 1)
        assert repo.delete_notify_channel_if(GUILD_ID, T.JoinLog, {"channel_id": 2}) == 0
        assert repo.delete_notify_channel_if(GUILD_ID, T.JoinLog, {"channel_id": 1}) == 1
        assert repo.get_notify_channel_fresh(GUILD_ID, T.JoinLog) is None

    def test_voice_log_cache_follows(self, repo):
        repo.cache.voice_log.load({})
        repo.insert_notify_channel(GUILD_ID, T.VoiceLog, 1, 2)
        assert repo.cache.voice_log.get(GUILD_ID) == (1, 2)
        repo.update_notify_channel_if(GUILD_ID, T.VoiceLog, {"channel_id": 1, "role_id": 2}, {"channel_id": 3, "role_id": None})
        assert repo.cache.voice_log.get(GUILD_ID) == (3, None)
        repo.delete_notify_channel_if(GUILD_ID, T.VoiceLog, {"channel_id": 3, "role_id": None})
        assert repo.cache.voice_log.get(GUILD_ID) is None


class TestEndpoints:
    @pytest.fixture
    def client(self, discord_env, repo, dashboard_env, monkeypatch) -> TestClient:  # noqa: F811
        seed_token(repo, dashboard_env.credential_id)
        make_session(repo)
        discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_CHANNELS)]
        monkeypatch.setattr(channel_notifies, "sqldb", repo)
        monkeypatch.setattr(sclient, "bot", fake_bot(fake_guild()))
        c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
        c.cookies.set("dashboard_session", "sid")
        c.repo = repo  # pyright: ignore[reportAttributeAccessIssue]
        return c

    def url(self, key: str) -> str:
        return f"/dashboard/guilds/{GUILD_ID}/channel-notifies/{key}"

    def put(self, client, key, values, original=None):
        return client.put(self.url(key), json={"values": values, "original": original}, headers={"Origin": FRONTEND})

    def delete(self, client, key, original):
        return client.request("DELETE", self.url(key), json={"original": original}, headers={"Origin": FRONTEND})

    def row(self, client, t):
        return client.repo.get_notify_channel_fresh(GUILD_ID, t)

    def test_create(self, client):
        res = self.put(client, "channel:1", {"channel_id": str(OK_CHANNEL), "role_id": str(OK_ROLE), "message": "ignored"})
        assert res.status_code == 200
        row = self.row(client, T.AllAnnouncements)
        assert (row.channel_id, row.role_id, row.message) == (OK_CHANNEL, OK_ROLE, None)  # 沒打勾的欄位不寫

    def test_create_only_used_fields(self, client):
        self.put(client, "channel:7", {"channel_id": str(OK_CHANNEL), "role_id": str(OK_ROLE), "message": "{member} hi"})
        row = self.row(client, T.MemberJoin)
        assert (row.role_id, row.message) == (None, "{member} hi")

    def test_blank_message_becomes_null(self, client):
        self.put(client, "channel:7", {"channel_id": str(OK_CHANNEL), "message": ""})
        assert self.row(client, T.MemberJoin).message is None

    def test_create_existing_returns_already_exists(self, client):
        client.repo.add_notify_channel(GUILD_ID, T.AllAnnouncements, OK_CHANNEL, OK_ROLE)
        res = self.put(client, "channel:1", {"channel_id": "15"})
        assert res.status_code == 409
        assert res.json() == {"error": "already_exists", "current": {"channel_id": str(OK_CHANNEL), "role_id": str(OK_ROLE)}}
        assert self.row(client, T.AllAnnouncements).channel_id == OK_CHANNEL

    def test_update_keeps_unused_role(self, client):
        # 指令替天氣預報設了身分組，網頁存檔後仍在
        client.repo.add_notify_channel(GUILD_ID, T.WeatherForecast, OK_CHANNEL, OK_ROLE)
        res = self.put(client, "channel:4", {"channel_id": "15"}, {"channel_id": str(OK_CHANNEL)})
        assert res.status_code == 200
        row = self.row(client, T.WeatherForecast)
        assert (row.channel_id, row.role_id) == (15, OK_ROLE)

    def test_update_conflict(self, client):
        client.repo.add_notify_channel(GUILD_ID, T.AllAnnouncements, OK_CHANNEL, OK_ROLE)
        # 別人已改成 15
        client.repo.add_notify_channel(GUILD_ID, T.AllAnnouncements, 15, OK_ROLE)
        res = self.put(
            client,
            "channel:1",
            {"channel_id": str(NO_HISTORY_CHANNEL), "role_id": None},
            {"channel_id": str(OK_CHANNEL), "role_id": str(OK_ROLE)},
        )
        assert res.status_code == 409
        assert res.json() == {"error": "conflict", "deleted": False, "current": {"channel_id": "15", "role_id": str(OK_ROLE)}}
        assert self.row(client, T.AllAnnouncements).channel_id == 15

    def test_overwrite_with_current_as_original(self, client):
        client.repo.add_notify_channel(GUILD_ID, T.AllAnnouncements, 15, None)
        res = self.put(client, "channel:1", {"channel_id": str(OK_CHANNEL)}, {"channel_id": "15", "role_id": None})
        assert res.status_code == 200
        assert self.row(client, T.AllAnnouncements).channel_id == OK_CHANNEL

    def test_update_deleted(self, client):
        res = self.put(client, "channel:1", {"channel_id": str(OK_CHANNEL)}, {"channel_id": "15", "role_id": None})
        assert res.status_code == 409
        assert res.json() == {"error": "conflict", "deleted": True, "current": None}

    def test_delete(self, client):
        client.repo.add_notify_channel(GUILD_ID, T.JoinLog, OK_CHANNEL)
        assert self.delete(client, "channel:6", {"channel_id": str(OK_CHANNEL)}).status_code == 200
        assert self.row(client, T.JoinLog) is None

    def test_delete_conflict(self, client):
        client.repo.add_notify_channel(GUILD_ID, T.JoinLog, 15)
        res = self.delete(client, "channel:6", {"channel_id": str(OK_CHANNEL)})
        assert res.status_code == 409
        assert res.json()["current"] == {"channel_id": "15"}
        assert self.row(client, T.JoinLog) is not None

    def test_delete_already_deleted(self, client):
        res = self.delete(client, "channel:6", {"channel_id": str(OK_CHANNEL)})
        assert res.json() == {"error": "conflict", "deleted": True, "current": None}

    @pytest.mark.parametrize(
        ("key", "values", "field"),
        [
            ("channel:1", {"channel_id": "999"}, "channel_id"),
            ("channel:1", {"channel_id": str(VOICE_CHANNEL)}, "channel_id"),
            ("channel:1", {"channel_id": str(NO_SEND_CHANNEL)}, "channel_id"),
            ("channel:4", {"channel_id": str(NO_HISTORY_CHANNEL)}, "channel_id"),  # 定時通知要 Read Message History
            ("channel:1", {"channel_id": str(OK_CHANNEL), "role_id": str(LOCKED_ROLE)}, "role_id"),
            ("channel:1", {"channel_id": str(OK_CHANNEL), "role_id": "999"}, "role_id"),
            ("channel:7", {"channel_id": str(OK_CHANNEL), "message": "x" * 2001}, "message"),
        ],
    )
    def test_invalid_field_rejected(self, client, key, values, field):
        res = self.put(client, key, values)
        assert res.status_code == 400
        assert res.json()["error"] == "invalid_field"
        assert res.json()["field"] == field
        assert res.json()["reason"]

    def test_unused_invalid_role_ignored(self, client):
        # 天氣預報不用身分組，送來的失效身分組不驗也不寫
        res = self.put(client, "channel:4", {"channel_id": str(OK_CHANNEL), "role_id": "999"})
        assert res.status_code == 200

    def test_clearing_invalid_role_ok(self, client):
        client.repo.add_notify_channel(GUILD_ID, T.AllAnnouncements, OK_CHANNEL, 999)
        res = self.put(client, "channel:1", {"channel_id": str(OK_CHANNEL), "role_id": None}, {"channel_id": str(OK_CHANNEL), "role_id": "999"})
        assert res.status_code == 200
        assert self.row(client, T.AllAnnouncements).role_id is None

    @pytest.mark.parametrize("key", ["channel:9", "community:1", "bogus"])
    def test_bad_type(self, client, key):
        assert self.put(client, key, {"channel_id": str(OK_CHANNEL)}).json() == {"error": "invalid_request"}

    def test_missing_channel_or_incomplete_original(self, client):
        assert self.put(client, "channel:1", {}).json() == {"error": "invalid_request"}
        assert self.put(client, "channel:1", {"channel_id": "1"}, {"channel_id": "1"}).json() == {"error": "invalid_request"}
        assert self.put(client, "channel:1", {"channel_id": "abc"}).json() == {"error": "invalid_request"}

    def test_bot_not_in_guild(self, client, monkeypatch):
        monkeypatch.setattr(sclient, "bot", fake_bot(None))
        res = self.put(client, "channel:1", {"channel_id": str(OK_CHANNEL)})
        assert (res.status_code, res.json()) == (404, {"error": "bot_not_in_guild"})

    def test_requires_origin(self, client):
        res = client.put(self.url("channel:1"), json={"values": {"channel_id": str(OK_CHANNEL)}})
        assert res.status_code == 400
