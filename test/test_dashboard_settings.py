"""伺服器管理後台 B-01：基本設定（語音時數開關與排行榜，假 Discord，真實 PostgreSQL）。"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from test_dashboard_auth import FRONTEND, dashboard_env, make_app, make_session  # noqa: F401  (fixture 與 helper)
from test_dashboard_guilds import MANAGE_CHANNELS, MANAGE_GUILD, g, seed_token
from test_dashboard_guilds import discord as discord_env  # noqa: F401  (fixture)
from test_dashboard_notifies import GUILD_ID, fake_bot
from test_identity import repo  # noqa: F401

from starDiscord.cmds import task as voice_task
from starlib import sclient
from starlib.database import GuildSetting, VoiceTime
from starServer.dashboard import settings

URL = f"/dashboard/guilds/{GUILD_ID}/settings"
ALICE, BOB, LEFT = 8001, 8002, 8003


class FakeGuild:
    def __init__(self):
        self.id = GUILD_ID
        self.me = SimpleNamespace(guild_permissions=SimpleNamespace(moderate_members=True))
        self.members = {
            ALICE: SimpleNamespace(display_name="愛麗絲", display_avatar=SimpleNamespace(url="https://cdn/a.png")),
            BOB: SimpleNamespace(display_name="鮑伯", display_avatar=SimpleNamespace(url="https://cdn/b.png")),
        }

    def get_member(self, uid: int):
        return self.members.get(uid)


@pytest.fixture
def client(discord_env, repo, dashboard_env, monkeypatch) -> TestClient:  # noqa: F811
    seed_token(repo, dashboard_env.credential_id)
    make_session(repo)
    discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_GUILD)]
    monkeypatch.setattr(settings, "sqldb", repo)
    monkeypatch.setattr(sclient, "bot", fake_bot(FakeGuild()))
    monkeypatch.setattr(voice_task, "voice_times", {})
    repo.cache.voice_time_counter.load([])
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
    c.cookies.set("dashboard_session", "sid")
    c.repo = repo  # pyright: ignore[reportAttributeAccessIssue]
    c.discord_env = discord_env  # pyright: ignore[reportAttributeAccessIssue]
    return c


def put(client, values: bool, original: bool):
    return put_fields(client, {"voice_time_counter": values}, {"voice_time_counter": original})


def put_fields(client, values: dict, original: dict):
    return client.put(URL, json={"values": values, "original": original}, headers={"Origin": FRONTEND})


def add_time(client, uid: int, minutes: int):
    client.repo.add(VoiceTime(discord_id=uid, guild_id=GUILD_ID, total_minute=timedelta(minutes=minutes)))


class TestGet:
    def test_no_setting_row_is_off_and_empty(self, client):
        assert client.get(URL).json() == {
            "voice_time_counter": False,
            "auto_timeout_enabled": False,
            "auto_timeout_times": 3,
            "auto_timeout_seconds": 600,
            "permission_issues": [],
            "leaderboard": [],
        }

    def test_null_column_is_off(self, client):
        client.repo.add(GuildSetting(guild_id=GUILD_ID, timeout_after_warning_times=None, voice_time_counter=None))
        assert client.get(URL).json()["voice_time_counter"] is False

    def test_on(self, client):
        client.repo.add(GuildSetting(guild_id=GUILD_ID, timeout_after_warning_times=None, voice_time_counter=True))
        assert client.get(URL).json()["voice_time_counter"] is True

    def test_leaderboard_sorted_with_minutes(self, client):
        add_time(client, BOB, 30)
        add_time(client, ALICE, 135)
        board = client.get(URL).json()["leaderboard"]
        assert [r["minutes"] for r in board] == [135, 30]
        assert board[0]["member"] == {"id": str(ALICE), "name": "愛麗絲", "avatar_url": "https://cdn/a.png", "left": False}

    def test_left_member_marked(self, client):
        add_time(client, LEFT, 10)
        member = client.get(URL).json()["leaderboard"][0]["member"]
        assert member == {"id": str(LEFT), "name": None, "avatar_url": None, "left": True}

    def test_limited_to_top_20(self, client):
        for i in range(25):
            add_time(client, 9000 + i, i + 1)
        board = client.get(URL).json()["leaderboard"]
        assert len(board) == 20
        assert board[0]["minutes"] == 25 and board[-1]["minutes"] == 6

    def test_other_guild_not_listed(self, client):
        client.repo.add(VoiceTime(discord_id=ALICE, guild_id=GUILD_ID + 1, total_minute=timedelta(minutes=99)))
        assert client.get(URL).json()["leaderboard"] == []

    def test_unsaved_minutes_added_to_db_total(self, client):
        add_time(client, ALICE, 60)
        voice_task.voice_times[GUILD_ID] = {ALICE: timedelta(minutes=7)}
        assert client.get(URL).json()["leaderboard"][0]["minutes"] == 67

    def test_unsaved_member_outside_db_top_20_can_enter(self, client):
        for i in range(20):
            add_time(client, 9000 + i, 100 + i)  # 100～119
        add_time(client, BOB, 95)  # 不在資料庫前 20 名
        voice_task.voice_times[GUILD_ID] = {BOB: timedelta(minutes=30), 424242: timedelta(minutes=5)}
        board = client.get(URL).json()["leaderboard"]
        assert len(board) == 20
        assert board[0]["member"]["id"] == str(BOB) and board[0]["minutes"] == 125
        assert "424242" not in [r["member"]["id"] for r in board]  # 5 分鐘進不了前 20

    def test_unsaved_only_member_listed(self, client):
        voice_task.voice_times[GUILD_ID] = {ALICE: timedelta(minutes=3)}
        board = client.get(URL).json()["leaderboard"]
        assert [(r["member"]["id"], r["minutes"]) for r in board] == [(str(ALICE), 3)]

    def test_requires_manage_guild(self, client):
        client.discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_CHANNELS)]
        assert client.get(URL).status_code == 403


class TestPut:
    def row(self, client):
        return client.repo.get_guild_setting_fresh(GUILD_ID)

    def test_enable_without_row_inserts_and_refreshes_cache(self, client):
        res = put(client, True, False)
        assert res.status_code == 200 and res.json()["voice_time_counter"] is True
        assert self.row(client).voice_time_counter is True
        assert GUILD_ID in client.repo.cache.voice_time_counter.raw()

    def test_disable_updates_and_refreshes_cache(self, client):
        put(client, True, False)
        res = put(client, False, True)
        assert res.status_code == 200 and res.json()["voice_time_counter"] is False
        assert self.row(client).voice_time_counter is False
        assert GUILD_ID not in client.repo.cache.voice_time_counter.raw()

    def test_null_column_matches_original_false(self, client):
        client.repo.add(GuildSetting(guild_id=GUILD_ID, timeout_after_warning_times=4, voice_time_counter=None))
        assert put(client, True, False).status_code == 200
        row = self.row(client)
        assert row.voice_time_counter is True and row.timeout_after_warning_times == 4  # 不覆蓋其他欄位

    def test_conflict_when_changed_by_others(self, client):
        client.repo.add(GuildSetting(guild_id=GUILD_ID, timeout_after_warning_times=None, voice_time_counter=True))
        res = put(client, True, False)  # 打開表單時是關的，現在已被別人開了
        assert res.status_code == 409
        assert res.json()["error"] == "conflict" and res.json()["deleted"] is False
        assert res.json()["current"] == {"voice_time_counter": True}  # 只回 original 有帶的欄位

    def test_conflict_when_no_row_but_original_true(self, client):
        assert put(client, False, True).status_code == 409

    def test_conflict_keeps_cache_untouched(self, client):
        client.repo.add(GuildSetting(guild_id=GUILD_ID, timeout_after_warning_times=None, voice_time_counter=True))
        client.repo.cache.voice_time_counter.load([GUILD_ID])
        put(client, False, False)
        assert client.repo.cache.voice_time_counter.raw() == [GUILD_ID]

    def test_requires_manage_guild(self, client):
        client.discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_CHANNELS)]
        assert put(client, True, False).status_code == 403
        assert self.row(client) is None

    def test_invalid_body(self, client):
        res = client.put(URL, json={"values": {}, "original": {}}, headers={"Origin": FRONTEND})
        assert res.status_code in (400, 422)


class TestAutoTimeout:
    def row(self, client):
        return client.repo.get_guild_setting_fresh(GUILD_ID)

    def test_get_returns_stored_values(self, client):
        client.repo.add(GuildSetting(guild_id=GUILD_ID, timeout_after_warning_times=5, voice_time_counter=None, auto_timeout_enabled=True, auto_timeout_seconds=900))
        body = client.get(URL).json()
        assert (body["auto_timeout_enabled"], body["auto_timeout_times"], body["auto_timeout_seconds"]) == (True, 5, 900)

    def test_get_null_columns_use_defaults(self, client):
        client.repo.add(GuildSetting(guild_id=GUILD_ID, timeout_after_warning_times=None, voice_time_counter=None, auto_timeout_enabled=True, auto_timeout_seconds=None))
        body = client.get(URL).json()
        assert (body["auto_timeout_times"], body["auto_timeout_seconds"]) == (3, 600)

    def test_permission_issue_when_bot_lacks_moderate_members(self, client, monkeypatch):
        guild = FakeGuild()
        guild.me.guild_permissions.moderate_members = False
        monkeypatch.setattr(sclient, "bot", fake_bot(guild))
        issues = client.get(URL).json()["permission_issues"]
        assert [i["permission"] for i in issues] == ["Moderate Members"]

    def test_enable_without_row_inserts(self, client):
        fields = {"auto_timeout_enabled": True, "auto_timeout_times": 2, "auto_timeout_seconds": 3600}
        original = {"auto_timeout_enabled": False, "auto_timeout_times": 3, "auto_timeout_seconds": 600}
        res = put_fields(client, fields, original)
        assert res.status_code == 200 and res.json()["auto_timeout_times"] == 2
        row = self.row(client)
        assert (row.auto_timeout_enabled, row.timeout_after_warning_times, row.auto_timeout_seconds) == (True, 2, 3600)

    def test_original_matches_defaults_when_columns_null(self, client):
        client.repo.add(GuildSetting(guild_id=GUILD_ID, timeout_after_warning_times=None, voice_time_counter=None, auto_timeout_enabled=False, auto_timeout_seconds=None))
        res = put_fields(client, {"auto_timeout_times": 4, "auto_timeout_seconds": 120}, {"auto_timeout_times": 3, "auto_timeout_seconds": 600})
        assert res.status_code == 200
        assert (self.row(client).timeout_after_warning_times, self.row(client).auto_timeout_seconds) == (4, 120)

    def test_each_form_only_touches_its_own_fields(self, client):
        client.repo.add(GuildSetting(guild_id=GUILD_ID, timeout_after_warning_times=5, voice_time_counter=False, auto_timeout_enabled=True, auto_timeout_seconds=900))
        assert put(client, True, False).status_code == 200
        row = self.row(client)
        assert (row.voice_time_counter, row.timeout_after_warning_times, row.auto_timeout_enabled, row.auto_timeout_seconds) == (True, 5, True, 900)
        assert put_fields(client, {"auto_timeout_enabled": False}, {"auto_timeout_enabled": True}).status_code == 200
        assert self.row(client).voice_time_counter is True

    def test_conflict_returns_only_compared_fields(self, client):
        client.repo.add(GuildSetting(guild_id=GUILD_ID, timeout_after_warning_times=7, voice_time_counter=None, auto_timeout_enabled=False, auto_timeout_seconds=None))
        res = put_fields(client, {"auto_timeout_times": 4}, {"auto_timeout_times": 3})
        assert res.status_code == 409 and res.json()["current"] == {"auto_timeout_times": 7}
        assert self.row(client).timeout_after_warning_times == 7

    @pytest.mark.parametrize(
        "values,field",
        [
            ({"auto_timeout_times": 0}, "auto_timeout_times"),
            ({"auto_timeout_times": 21}, "auto_timeout_times"),
            ({"auto_timeout_seconds": 59}, "auto_timeout_seconds"),
            ({"auto_timeout_seconds": 604801}, "auto_timeout_seconds"),
            ({"auto_timeout_seconds": 90}, "auto_timeout_seconds"),
            ({"auto_timeout_seconds": 3601}, "auto_timeout_seconds"),
        ],
    )
    def test_range_validation(self, client, values, field):
        res = put_fields(client, values, {k: 3 for k in values})
        assert res.status_code == 400 and res.json()["field"] == field
        assert self.row(client) is None

    @pytest.mark.parametrize("values,original", [({}, {}), ({"auto_timeout_times": 3}, {}), ({"auto_timeout_times": 3}, {"voice_time_counter": False})])
    def test_values_must_be_covered_by_original(self, client, values, original):
        assert put_fields(client, values, original).status_code == 400

    def test_boundaries_accepted(self, client):
        res = put_fields(client, {"auto_timeout_times": 20, "auto_timeout_seconds": 604800}, {"auto_timeout_times": 3, "auto_timeout_seconds": 600})
        assert res.status_code == 200
        assert put_fields(client, {"auto_timeout_times": 1, "auto_timeout_seconds": 60}, {"auto_timeout_times": 20, "auto_timeout_seconds": 604800}).status_code == 200
