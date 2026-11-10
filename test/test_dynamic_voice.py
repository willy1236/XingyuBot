"""動態語音 S-01：bot 權限檢查、模板規則，以及大廳寫入與 cache 同步。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import inspect, update
from test_identity import repo  # noqa: F401  (fixture)

from starlib.database.postgresql.models import DynamicVoiceLobby
from starlib.dynamic_voice import LobbyPermIssue, lobby_permission_issues, normalize_room_template, room_template_too_long
from starlib.exceptions import DataExistError

GUILD_ID = 1001
OTHER_GUILD_ID = 1002


def perms(**missing: bool) -> SimpleNamespace:
    values = dict(manage_channels=True, manage_roles=True, move_members=True, send_messages=True, view_channel=True)
    values.update({k: False for k in missing})
    return SimpleNamespace(**values)


def lobby_channel(*, category_missing=(), channel_missing=(), guild_missing=(), has_category=True) -> SimpleNamespace:
    category = SimpleNamespace(permissions_for=lambda _me: perms(**dict.fromkeys(category_missing, True))) if has_category else None
    me = SimpleNamespace(guild_permissions=perms(**dict.fromkeys(guild_missing, True)))
    return SimpleNamespace(
        guild=SimpleNamespace(me=me),
        category=category,
        permissions_for=lambda _me: perms(**dict.fromkeys(channel_missing, True)),
    )


class TestLobbyPermissionIssues:
    def test_all_granted(self):
        assert lobby_permission_issues(lobby_channel()) == []

    def test_category_missing_move_members(self):
        issues = lobby_permission_issues(lobby_channel(channel_missing=["move_members"]))
        assert issues == [LobbyPermIssue("Move Members", "channel", "無法把進入大廳的人移進房間")]

    def test_no_category_checks_guild_level_manage_channels(self):
        issues = lobby_permission_issues(lobby_channel(has_category=False, guild_missing=["manage_channels"]))
        assert issues == [LobbyPermIssue("Manage Channels", "guild", "無法建立房間")]

    def test_category_manage_channels_ignores_guild_level(self):
        # 有分類時只看分類，伺服器層級缺權限不算
        assert lobby_permission_issues(lobby_channel(guild_missing=["manage_channels"])) == []
        issues = lobby_permission_issues(lobby_channel(category_missing=["manage_channels"]))
        assert [(i.permission, i.scope) for i in issues] == [("Manage Channels", "category")]

    def test_order_follows_spec_table(self):
        issues = lobby_permission_issues(
            lobby_channel(
                category_missing=["manage_channels"],
                channel_missing=["view_channel", "send_messages", "move_members", "manage_roles"],
            )
        )
        assert [i.permission for i in issues] == ["Manage Channels", "Manage Roles", "Move Members", "Send Messages", "View Channel"]


class TestTemplateRules:
    @pytest.mark.parametrize(("raw", "expected"), [(None, None), ("", None), ("   ", None), ("  {member} 的房間 ", "{member} 的房間")])
    def test_normalize(self, raw, expected):
        assert normalize_room_template(raw) == expected

    def test_too_long_boundary(self):
        assert room_template_too_long("{member}" + "x" * 68) is False  # 32 + 68 = 100
        assert room_template_too_long("{member}" + "x" * 69) is True
        assert room_template_too_long(None) is False

    def test_plain_template_counts_characters(self):
        assert room_template_too_long("x" * 100) is False
        assert room_template_too_long("x" * 101) is True

    def test_counts_code_points_not_bytes(self):
        assert room_template_too_long("房" * 100) is False


class TestLobbyRepository:
    @pytest.fixture(autouse=True)
    def _cache(self, repo):  # noqa: F811
        repo.cache.dynamic_voice_lobby.load({})
        repo.cache.dynamic_voice_room.load([])

    def keys(self, repo):
        return set(repo.cache.dynamic_voice_lobby.raw())

    def test_replace_lobby_leaves_only_new_in_cache(self, repo):  # noqa: F811
        repo.add_dynamic_voice_lobby(GUILD_ID, 1, "a")
        repo.add_dynamic_voice_lobby(GUILD_ID, 2, "b")
        assert self.keys(repo) == {2}
        assert repo.cache.dynamic_voice_lobby.get(2).default_room_name == "b"

    def test_other_guild_lobby_untouched(self, repo):  # noqa: F811
        repo.add_dynamic_voice_lobby(OTHER_GUILD_ID, 9)
        repo.add_dynamic_voice_lobby(GUILD_ID, 1)
        repo.add_dynamic_voice_lobby(GUILD_ID, 2)
        assert self.keys(repo) == {2, 9}

    def test_cache_values_are_transient(self, repo):  # noqa: F811
        repo.add_dynamic_voice_lobby(GUILD_ID, 1, "a")
        assert inspect(repo.cache.dynamic_voice_lobby.get(1)).transient
        repo.delete_dynamic_voice_lobby_if(GUILD_ID, {"channel_id": 1})
        repo.insert_dynamic_voice_lobby(GUILD_ID, 3, "c")
        assert inspect(repo.cache.dynamic_voice_lobby.get(3)).transient
        assert repo.update_dynamic_voice_lobby_if(GUILD_ID, {"channel_id": 3}, {"channel_id": 4, "default_room_name": "d"}) == 1
        assert inspect(repo.cache.dynamic_voice_lobby.get(4)).transient
        assert repo.cache.dynamic_voice_lobby.get(4).default_room_name == "d"

    def test_remove_uses_fresh_value_when_session_is_stale(self, repo):  # noqa: F811
        repo.add_dynamic_voice_lobby(GUILD_ID, 1)
        # bot thread 的 session 留著 A：載入後，另一個 thread 把它換成 B（Core 更新不會刷新 identity map）
        stale = repo.get_dynamic_voice_lobby(GUILD_ID)  # identity map 是弱參照，要留著
        assert stale.channel_id == 1
        repo.session.connection().execute(
            update(DynamicVoiceLobby.__table__).where(DynamicVoiceLobby.__table__.c.guild_id == GUILD_ID).values(channel_id=2)
        )
        repo.cache.dynamic_voice_lobby.delete(1)
        repo.cache.dynamic_voice_lobby.set(2, DynamicVoiceLobby(guild_id=GUILD_ID, channel_id=2, default_room_name=None))
        assert repo.get_dynamic_voice_lobby(GUILD_ID).channel_id == 1  # session 裡仍是舊值
        assert stale.channel_id == 1
        repo.remove_dynamic_voice_lobby(GUILD_ID)
        assert self.keys(repo) == set()

    def test_conditional_write_drops_cache_key_of_original(self, repo):  # noqa: F811
        # cache 的舊 key 取自 original，不是事前讀到的值：事前讀取與 original 不同（被別的 thread 搶先改過）時也刪對
        repo.add_dynamic_voice_lobby(GUILD_ID, 1)
        repo.cache.dynamic_voice_lobby.set(7, DynamicVoiceLobby(guild_id=GUILD_ID, channel_id=7, default_room_name=None))
        assert repo.update_dynamic_voice_lobby_if(GUILD_ID, {"channel_id": 1}, {"channel_id": 2}) == 1
        assert self.keys(repo) == {2, 7}  # 刪的是 original 的 1，沒有碰其他 key
        assert repo.delete_dynamic_voice_lobby_if(GUILD_ID, {"channel_id": 2}) == 1
        assert self.keys(repo) == {7}

    def test_remove_clears_cache(self, repo):  # noqa: F811
        repo.add_dynamic_voice_lobby(GUILD_ID, 1)
        repo.remove_dynamic_voice_lobby(GUILD_ID)
        assert self.keys(repo) == set()
        assert repo.get_dynamic_voice_lobby_fresh(GUILD_ID) is None

    def test_insert_does_not_overwrite(self, repo):  # noqa: F811
        repo.insert_dynamic_voice_lobby(GUILD_ID, 1, "a")
        with pytest.raises(DataExistError):
            repo.insert_dynamic_voice_lobby(GUILD_ID, 2, "b")
        row = repo.get_dynamic_voice_lobby_fresh(GUILD_ID)
        assert (row.channel_id, row.default_room_name) == (1, "a")
        assert self.keys(repo) == {1}

    def test_update_if_mismatch_returns_zero_and_keeps_cache(self, repo):  # noqa: F811
        repo.add_dynamic_voice_lobby(GUILD_ID, 1, "a")
        assert repo.update_dynamic_voice_lobby_if(GUILD_ID, {"channel_id": 9, "default_room_name": "a"}, {"channel_id": 2}) == 0
        assert self.keys(repo) == {1}
        assert repo.cache.dynamic_voice_lobby.get(1).default_room_name == "a"

    def test_update_if_matches_null(self, repo):  # noqa: F811
        repo.add_dynamic_voice_lobby(GUILD_ID, 1, None)
        assert repo.update_dynamic_voice_lobby_if(GUILD_ID, {"channel_id": 1, "default_room_name": None}, {"channel_id": 2, "default_room_name": "x"}) == 1
        assert self.keys(repo) == {2}

    def test_delete_if_mismatch_returns_zero_and_keeps_cache(self, repo):  # noqa: F811
        repo.add_dynamic_voice_lobby(GUILD_ID, 1, "a")
        assert repo.delete_dynamic_voice_lobby_if(GUILD_ID, {"channel_id": 9}) == 0
        assert self.keys(repo) == {1}
        assert repo.delete_dynamic_voice_lobby_if(GUILD_ID, {"channel_id": 1, "default_room_name": "a"}) == 1
        assert self.keys(repo) == set()

    def test_rooms_fresh_only_that_guild(self, repo):  # noqa: F811
        repo.add_dynamic_voice(11, 1, GUILD_ID)
        repo.add_dynamic_voice(12, 1, OTHER_GUILD_ID)
        assert [r.channel_id for r in repo.get_dynamic_voice_rooms_fresh(GUILD_ID)] == [11]

