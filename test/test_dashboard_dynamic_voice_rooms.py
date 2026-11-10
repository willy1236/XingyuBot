"""動態語音後台 T-04、T-05：房間清單與清除空房。"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import discord
import pytest
from fastapi.testclient import TestClient
from test_dashboard_auth import FRONTEND, dashboard_env, make_app, make_session  # noqa: F401  (fixture 與 helper)
from test_dashboard_guilds import MANAGE_CHANNELS, g, seed_token
from test_dashboard_guilds import discord as discord_env  # noqa: F401  (fixture)
from test_dashboard_notifies import GUILD_ID, fake_bot
from test_identity import repo  # noqa: F401

from starlib import sclient
from starServer.dashboard import dynamic_voice_rooms

CREATOR = 7001
URL = f"/dashboard/guilds/{GUILD_ID}/dynamic-voice/rooms"


def http_error(cls, status: int, text: str = "error"):
    return cls(SimpleNamespace(status=status, reason=text), text)


class FakeRoom:
    def __init__(self, cid: int, name: str, members: int = 0, created_hour: int = 0, delete_error: Exception | None = None):
        self.id = cid
        self.name = name
        self.members = [object()] * members
        self.created_at = datetime(2026, 11, 10, created_hour, tzinfo=UTC)
        self.delete_error = delete_error
        self.deleted = False

    async def delete(self, *, reason: str | None = None):
        if self.delete_error is not None:
            raise self.delete_error
        self.deleted = True


class FakeGuild:
    def __init__(self, cached: list[FakeRoom], uncached: list[FakeRoom] = (), fetch_error: Exception | None = None):
        self.id = GUILD_ID
        self._cached = {r.id: r for r in cached}
        self._uncached = {r.id: r for r in uncached}
        self.fetch_error = fetch_error
        self.members = {CREATOR: SimpleNamespace(display_name="建立者", display_avatar=SimpleNamespace(url="https://cdn/a.png"))}
        self.fetch_calls: list[int] = []

    def get_channel(self, cid: int):
        return self._cached.get(cid)

    def get_member(self, uid: int):
        return self.members.get(uid)

    async def fetch_channel(self, cid: int):
        self.fetch_calls.append(cid)
        if self.fetch_error is not None:
            raise self.fetch_error
        if cid in self._uncached:
            return self._uncached[cid]
        raise http_error(discord.NotFound, 404, "Unknown Channel")


@pytest.fixture
def client(discord_env, repo, dashboard_env, monkeypatch) -> TestClient:  # noqa: F811
    seed_token(repo, dashboard_env.credential_id)
    make_session(repo)
    discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_CHANNELS)]
    monkeypatch.setattr(dynamic_voice_rooms, "sqldb", repo)
    repo.cache.dynamic_voice_room.load([])
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
    c.cookies.set("dashboard_session", "sid")
    c.repo = repo  # pyright: ignore[reportAttributeAccessIssue]
    c.discord_env = discord_env  # pyright: ignore[reportAttributeAccessIssue]
    c.monkeypatch = monkeypatch  # pyright: ignore[reportAttributeAccessIssue]
    return c


def use_guild(client, guild):
    client.monkeypatch.setattr(sclient, "bot", fake_bot(guild))


def add_record(client, cid: int, creator: int = CREATOR):
    client.repo.add_dynamic_voice(cid, creator, GUILD_ID)


class TestListRooms:
    def test_empty(self, client):
        use_guild(client, FakeGuild([]))
        assert client.get(URL).json() == {"rooms": []}

    def test_room_fields_and_order(self, client):
        use_guild(client, FakeGuild([FakeRoom(2, "晚的房間", 3, created_hour=9), FakeRoom(1, "早的房間", 0, created_hour=1)]))
        add_record(client, 2)
        add_record(client, 1)
        rooms = client.get(URL).json()["rooms"]
        assert [r["id"] for r in rooms] == ["1", "2"]  # 依建立時間排序
        assert rooms[1] == {
            "id": "2",
            "name": "晚的房間",
            "member_count": 3,
            "created_at": "2026-11-10T09:00:00+00:00",
            "creator": {"name": "建立者", "avatar_url": "https://cdn/a.png"},
        }

    def test_creator_left_guild(self, client):
        use_guild(client, FakeGuild([FakeRoom(1, "房間")]))
        add_record(client, 1, creator=9999)
        assert client.get(URL).json()["rooms"][0]["creator"] is None

    def test_only_this_guild(self, client):
        use_guild(client, FakeGuild([FakeRoom(1, "房間")]))
        add_record(client, 1)
        client.repo.add_dynamic_voice(2, CREATOR, GUILD_ID + 1)
        assert [r["id"] for r in client.get(URL).json()["rooms"]] == ["1"]

    def test_deleted_channel_record_is_removed_and_hidden(self, client):
        guild = FakeGuild([FakeRoom(1, "房間")])
        use_guild(client, guild)
        add_record(client, 1)
        add_record(client, 2)  # Discord 上已不存在
        assert [r["id"] for r in client.get(URL).json()["rooms"]] == ["1"]
        assert guild.fetch_calls == [2]
        assert [r.channel_id for r in client.repo.get_dynamic_voice_rooms_fresh(GUILD_ID)] == [1]
        assert 2 not in client.repo.cache.dynamic_voice_room

    def test_not_yet_in_gateway_cache_is_kept(self, client):
        # 剛開的房間：get_channel 還沒有，fetch_channel 找得到，紀錄不能刪
        use_guild(client, FakeGuild([], uncached=[FakeRoom(1, "新房間", 1)]))
        add_record(client, 1)
        assert [r["id"] for r in client.get(URL).json()["rooms"]] == ["1"]
        assert [r.channel_id for r in client.repo.get_dynamic_voice_rooms_fresh(GUILD_ID)] == [1]

    def test_unresolvable_channel_is_neither_shown_nor_removed(self, client):
        use_guild(client, FakeGuild([], fetch_error=http_error(discord.HTTPException, 500)))
        add_record(client, 1)
        assert client.get(URL).json() == {"rooms": []}
        assert [r.channel_id for r in client.repo.get_dynamic_voice_rooms_fresh(GUILD_ID)] == [1]

    def test_lobby_removal_does_not_hide_rooms(self, client):
        use_guild(client, FakeGuild([FakeRoom(1, "房間")]))
        add_record(client, 1)
        client.repo.add_dynamic_voice_lobby(GUILD_ID, 50)
        client.repo.remove_dynamic_voice_lobby(GUILD_ID)
        assert [r["id"] for r in client.get(URL).json()["rooms"]] == ["1"]

    def test_requires_manage_channels(self, client):
        use_guild(client, FakeGuild([]))
        client.discord_env.guilds = [g(str(GUILD_ID), "guild", 0)]
        assert client.get(URL).status_code == 403

    def test_bot_not_in_guild(self, client):
        client.monkeypatch.setattr(sclient, "bot", fake_bot(None))
        assert client.get(URL).status_code == 404


class TestClearRooms:
    def post(self, client, ids):
        return client.post(f"{URL}/clear", json={"channel_ids": [str(i) for i in ids]}, headers={"Origin": FRONTEND})

    def remaining(self, client):
        return sorted(r.channel_id for r in client.repo.get_dynamic_voice_rooms_fresh(GUILD_ID))

    def results(self, res):
        return {r["id"]: r for r in res.json()["results"]}

    def test_clears_empty_and_skips_occupied(self, client):
        empty1, empty2, busy = FakeRoom(1, "空1"), FakeRoom(2, "空2"), FakeRoom(3, "有人", members=2)
        use_guild(client, FakeGuild([empty1, empty2, busy]))
        for r in (empty1, empty2, busy):
            add_record(client, r.id)
        res = self.post(client, [1, 2, 3])
        assert res.status_code == 200
        out = self.results(res)
        assert [out[k]["status"] for k in ("1", "2", "3")] == ["cleared", "cleared", "skipped_occupied"]
        assert (empty1.deleted, empty2.deleted, busy.deleted) == (True, True, False)
        assert self.remaining(client) == [3]
        assert 1 not in client.repo.cache.dynamic_voice_room

    def test_result_has_name(self, client):
        use_guild(client, FakeGuild([FakeRoom(1, "空房")]))
        add_record(client, 1)
        assert self.post(client, [1]).json() == {"results": [{"id": "1", "name": "空房", "status": "cleared"}]}

    def test_forbidden_fails_that_room_only(self, client):
        locked = FakeRoom(1, "刪不掉", delete_error=http_error(discord.Forbidden, 403, "Missing Permissions"))
        fine = FakeRoom(2, "可以")
        use_guild(client, FakeGuild([locked, fine]))
        add_record(client, 1)
        add_record(client, 2)
        out = self.results(self.post(client, [1, 2]))
        assert out["1"] == {"id": "1", "name": "刪不掉", "status": "failed", "reason": "bot 沒有刪除這個頻道的權限"}
        assert out["2"]["status"] == "cleared"
        assert self.remaining(client) == [1]  # 失敗的紀錄保留

    def test_other_http_error_carries_discord_message(self, client):
        broken = FakeRoom(1, "壞掉", delete_error=http_error(discord.HTTPException, 500, "Internal Error"))
        use_guild(client, FakeGuild([broken]))
        add_record(client, 1)
        out = self.results(self.post(client, [1]))
        assert out["1"]["status"] == "failed"
        assert "Internal Error" in out["1"]["reason"]

    def test_already_gone_counts_as_cleared(self, client):
        use_guild(client, FakeGuild([]))
        add_record(client, 1)
        assert self.results(self.post(client, [1]))["1"]["status"] == "cleared"
        assert self.remaining(client) == []

    def test_delete_not_found_counts_as_cleared(self, client):
        gone = FakeRoom(1, "剛被刪", delete_error=http_error(discord.NotFound, 404))
        use_guild(client, FakeGuild([gone]))
        add_record(client, 1)
        assert self.results(self.post(client, [1]))["1"]["status"] == "cleared"
        assert self.remaining(client) == []

    def test_not_a_dynamic_room_is_failed_and_untouched(self, client):
        other = FakeRoom(9, "一般頻道")
        use_guild(client, FakeGuild([other]))
        out = self.results(self.post(client, [9]))
        assert out["9"] == {"id": "9", "name": None, "status": "failed", "reason": "不是動態房間"}
        assert other.deleted is False

    def test_other_guild_room_is_rejected(self, client):
        other = FakeRoom(9, "別的伺服器的房間")
        use_guild(client, FakeGuild([other]))
        client.repo.add_dynamic_voice(9, CREATOR, GUILD_ID + 1)
        assert self.results(self.post(client, [9]))["9"]["status"] == "failed"
        assert other.deleted is False

    def test_duplicate_ids_processed_once(self, client):
        room = FakeRoom(1, "空房")
        use_guild(client, FakeGuild([room]))
        add_record(client, 1)
        assert len(self.post(client, [1, 1]).json()["results"]) == 1

    def test_empty_request_rejected(self, client):
        use_guild(client, FakeGuild([]))
        assert self.post(client, []).status_code == 400

    def test_too_many_ids_rejected(self, client):
        use_guild(client, FakeGuild([]))
        assert self.post(client, list(range(1, 102))).status_code == 400
        assert self.post(client, list(range(1, 101))).status_code == 200

    def test_invalid_id_rejected(self, client):
        use_guild(client, FakeGuild([]))
        res = client.post(f"{URL}/clear", json={"channel_ids": ["abc"]}, headers={"Origin": FRONTEND})
        assert res.status_code == 400

    def test_requires_manage_channels(self, client):
        room = FakeRoom(1, "空房")
        use_guild(client, FakeGuild([room]))
        add_record(client, 1)
        client.discord_env.guilds = [g(str(GUILD_ID), "guild", 0)]
        assert self.post(client, [1]).status_code == 403
        assert room.deleted is False
