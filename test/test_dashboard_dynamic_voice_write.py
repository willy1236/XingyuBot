"""動態語音後台 T-02：選項與大廳的新增、修改、移除。"""

from __future__ import annotations

import pytest
from test_dashboard_auth import FRONTEND, dashboard_env  # noqa: F401  (fixture)
from test_dashboard_dynamic_voice import (  # noqa: F401  (client 是 fixture)
    GUILD_ID,
    LOBBY,
    NO_CATEGORY_LOBBY,
    OTHER_LOBBY,
    STAGE_CHANNEL,
    TEXT_CHANNEL,
    URL,
    client,
    fake_voice_guild,
    use_guild,
)
from test_dashboard_guilds import g
from test_dashboard_guilds import discord as discord_env  # noqa: F401  (fixture)
from test_identity import repo  # noqa: F401


class TestOptions:
    def get(self, client):
        return client.get(f"{URL}/options")

    def test_lists_voice_channels_only(self, client):
        body = self.get(client).json()
        assert [c["id"] for c in body["channels"]] == [str(LOBBY), str(OTHER_LOBBY), str(NO_CATEGORY_LOBBY)]
        assert body["channels"][0] == {"id": str(LOBBY), "name": "大廳", "category": "遊戲", "permission_issues": []}
        assert body["channels"][2]["category"] is None  # 沒有分類的也在選單裡

    def test_excludes_existing_dynamic_rooms(self, client):
        client.repo.add_dynamic_voice(OTHER_LOBBY, 1, GUILD_ID)
        assert OTHER_LOBBY not in [int(c["id"]) for c in self.get(client).json()["channels"]]

    def test_permission_issues_per_channel(self, client, monkeypatch):
        use_guild(monkeypatch, fake_voice_guild(lobby=["move_members"]))
        first = self.get(client).json()["channels"][0]
        assert [i["permission"] for i in first["permission_issues"]] == ["Move Members"]

    def test_username_is_member_name(self, client):
        assert self.get(client).json()["username"] == "willy"

    def test_username_null_when_member_missing(self, client, monkeypatch):
        guild = fake_voice_guild()
        guild.get_member = lambda _uid: None
        use_guild(monkeypatch, guild)
        assert self.get(client).json()["username"] is None

    def test_requires_manage_channels(self, client):
        client.discord_env.guilds = [g(str(GUILD_ID), "guild", 0)]
        assert self.get(client).status_code == 403


class TestWrite:
    def put(self, client, values, original=None):
        return client.put(URL, json={"values": values, "original": original}, headers={"Origin": FRONTEND})

    def delete(self, client, original):
        return client.request("DELETE", URL, json={"original": original}, headers={"Origin": FRONTEND})

    def row(self, client):
        return client.repo.get_dynamic_voice_lobby_fresh(GUILD_ID)

    def cache_keys(self, client):
        return set(client.repo.cache.dynamic_voice_lobby.raw())

    def test_create_takes_effect_in_cache(self, client):
        res = self.put(client, {"channel_id": str(LOBBY), "template": "  {member} 的房間 "})
        assert res.status_code == 200
        assert res.json()["lobby"]["template"] == "{member} 的房間"
        assert res.json()["lobby"]["channel"]["name"] == "大廳"
        assert self.row(client).default_room_name == "{member} 的房間"  # 正規化後才寫入
        assert self.cache_keys(client) == {LOBBY}

    def test_blank_template_becomes_null(self, client):
        self.put(client, {"channel_id": str(LOBBY), "template": "   "})
        assert self.row(client).default_room_name is None

    def test_create_without_category(self, client):
        assert self.put(client, {"channel_id": str(NO_CATEGORY_LOBBY), "template": None}).status_code == 200

    def test_replace_lobby_stops_old_one(self, client):
        client.repo.add_dynamic_voice_lobby(GUILD_ID, LOBBY, "a")
        res = self.put(client, {"channel_id": str(OTHER_LOBBY), "template": "b"}, {"channel_id": str(LOBBY), "template": "a"})
        assert res.status_code == 200
        assert self.cache_keys(client) == {OTHER_LOBBY}

    def test_missing_permissions_still_saves(self, client, monkeypatch):
        use_guild(monkeypatch, fake_voice_guild(lobby=["move_members"]))
        res = self.put(client, {"channel_id": str(LOBBY), "template": None})
        assert res.status_code == 200
        assert res.json()["lobby"]["permission_issues"][0]["permission"] == "Move Members"

    def test_create_existing_returns_already_exists(self, client):
        client.repo.add_dynamic_voice_lobby(GUILD_ID, OTHER_LOBBY, "x")
        res = self.put(client, {"channel_id": str(LOBBY), "template": None})
        assert res.status_code == 409
        assert res.json() == {"error": "already_exists", "current": {"channel_id": str(OTHER_LOBBY), "template": "x"}}
        assert self.cache_keys(client) == {OTHER_LOBBY}

    def test_update_conflict_when_command_changed_it(self, client):
        client.repo.add_dynamic_voice_lobby(GUILD_ID, LOBBY, "a")
        client.repo.add_dynamic_voice_lobby(GUILD_ID, OTHER_LOBBY, "a")  # 指令換了大廳
        res = self.put(client, {"channel_id": str(NO_CATEGORY_LOBBY), "template": None}, {"channel_id": str(LOBBY), "template": "a"})
        assert res.status_code == 409
        assert res.json() == {"error": "conflict", "deleted": False, "current": {"channel_id": str(OTHER_LOBBY), "template": "a"}}
        assert self.cache_keys(client) == {OTHER_LOBBY}

    def test_update_deleted(self, client):
        res = self.put(client, {"channel_id": str(LOBBY), "template": None}, {"channel_id": str(OTHER_LOBBY), "template": None})
        assert (res.status_code, res.json()) == (409, {"error": "conflict", "deleted": True, "current": None})

    def test_overwrite_with_current_as_original(self, client):
        client.repo.add_dynamic_voice_lobby(GUILD_ID, OTHER_LOBBY, None)
        res = self.put(client, {"channel_id": str(LOBBY), "template": "mine"}, {"channel_id": str(OTHER_LOBBY), "template": None})
        assert res.status_code == 200
        assert self.cache_keys(client) == {LOBBY}

    def test_original_template_is_compared_raw(self, client):
        # 指令存了帶空白的值；網頁拿 GET 的原始值當 original，不會被誤判成衝突
        client.repo.add_dynamic_voice_lobby(GUILD_ID, LOBBY, " a ")
        res = self.put(client, {"channel_id": str(LOBBY), "template": "a"}, {"channel_id": str(LOBBY), "template": " a "})
        assert res.status_code == 200

    @pytest.mark.parametrize("cid", [str(TEXT_CHANNEL), str(STAGE_CHANNEL), "99999", "abc"])
    def test_rejects_non_voice_or_unknown_channel(self, client, cid):
        res = self.put(client, {"channel_id": cid, "template": None})
        assert res.status_code == 400
        assert res.json()["error"] == "invalid_request"
        assert self.row(client) is None

    def test_rejects_dynamic_room(self, client):
        client.repo.add_dynamic_voice(OTHER_LOBBY, 1, GUILD_ID)
        assert self.put(client, {"channel_id": str(OTHER_LOBBY), "template": None}).status_code == 400

    def test_rejects_too_long_template(self, client):
        res = self.put(client, {"channel_id": str(LOBBY), "template": "{member}" + "x" * 69})
        assert (res.status_code, res.json()) == (400, {"error": "invalid_request", "field": "template"})
        assert self.put(client, {"channel_id": str(LOBBY), "template": "{member}" + "x" * 68}).status_code == 200

    def test_rejects_malformed_body(self, client):
        assert client.put(URL, json={"values": {}}, headers={"Origin": FRONTEND}).status_code == 400

    def test_delete(self, client):
        client.repo.add_dynamic_voice_lobby(GUILD_ID, LOBBY, "a")
        assert self.delete(client, {"channel_id": str(LOBBY), "template": "a"}).status_code == 200
        assert self.row(client) is None
        assert self.cache_keys(client) == set()

    def test_delete_conflict(self, client):
        client.repo.add_dynamic_voice_lobby(GUILD_ID, LOBBY, "a")
        res = self.delete(client, {"channel_id": str(LOBBY), "template": "changed"})
        assert res.status_code == 409
        assert res.json() == {"error": "conflict", "deleted": False, "current": {"channel_id": str(LOBBY), "template": "a"}}
        assert self.cache_keys(client) == {LOBBY}

    def test_delete_already_removed(self, client):
        res = self.delete(client, {"channel_id": str(LOBBY), "template": None})
        assert (res.status_code, res.json()) == (409, {"error": "conflict", "deleted": True, "current": None})

    def test_replaced_on_web_then_removed_by_command_stops_new_lobby(self, client):
        self.put(client, {"channel_id": str(LOBBY), "template": None})
        self.put(client, {"channel_id": str(OTHER_LOBBY), "template": None}, {"channel_id": str(LOBBY), "template": None})
        client.repo.remove_dynamic_voice_lobby(GUILD_ID)
        assert self.cache_keys(client) == set()

    def test_no_permission(self, client):
        client.discord_env.guilds = [g(str(GUILD_ID), "guild", 0)]
        assert self.put(client, {"channel_id": str(LOBBY), "template": None}).status_code == 403
        assert self.delete(client, {"channel_id": str(LOBBY), "template": None}).status_code == 403
        assert self.row(client) is None
