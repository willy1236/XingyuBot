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
    return client.put(
        URL,
        json={"values": {"voice_time_counter": values}, "original": {"voice_time_counter": original}},
        headers={"Origin": FRONTEND},
    )


def add_time(client, uid: int, minutes: int):
    client.repo.add(VoiceTime(discord_id=uid, guild_id=GUILD_ID, total_minute=timedelta(minutes=minutes)))


class TestGet:
    def test_no_setting_row_is_off_and_empty(self, client):
        assert client.get(URL).json() == {"voice_time_counter": False, "leaderboard": []}

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
        assert res.json()["current"] == {"voice_time_counter": True}

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
