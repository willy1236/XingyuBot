"""私人頻道的共用規則（starlib/tickets.py）：前綴、預設內容、權限覆寫、套用管理身分組。"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import discord
import pytest

from starlib.tickets import (
    apply_manager_role_changes,
    build_ticket_overwrites,
    category_permission_issues,
    default_lobby_content,
    lobby_channel_permission_issues,
    locked_overwrite,
    normalize_prefix,
    open_overwrite,
    prefix_error,
)

CLOSED = datetime(2026, 1, 1, tzinfo=UTC)


class TestPrefix:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("ticket", "ticket"),
            ("Report Case", "report-case"),
            ("  a   b  ", "a-b"),
            ("檢舉 Case_1", "檢舉-case_1"),
            ("a!@#b", "ab"),
            ("--x--y--", "x-y"),
            ("a--b", "a-b"),
        ],
    )
    def test_normalize(self, raw, expected):
        assert normalize_prefix(raw) == expected

    def test_valid(self):
        assert prefix_error("report") is None
        assert prefix_error("a" * 20) is None

    @pytest.mark.parametrize("raw", ["", "   ", "!!!", "a" * 21, "a " * 11])
    def test_invalid(self, raw):
        assert prefix_error(raw) is not None


def test_default_content_matches_legacy_setup():
    c = default_lobby_content("https://cdn/avatar.png")
    assert c.content is None
    assert c.embed is not None
    assert c.embed.description == "點擊下方按鈕以建立私人頻道"
    assert c.embed.author is not None
    assert (c.embed.author.name, c.embed.author.icon_url) == ("私人頻道系統", "https://cdn/avatar.png")
    assert c.embed.color == 0xC4E9FF


class Member:
    def __init__(self, uid: int):
        self.id = uid


class FakeRole:
    def __init__(self, rid: int):
        self.id = rid


class FakeChannel:
    def __init__(self, cid: int, **perms):
        self.id = cid
        self.perms = perms
        self.calls: list[tuple[int, object, str | None]] = []
        self.error: Exception | None = None

    def permissions_for(self, _member):
        return SimpleNamespace(**self.perms)

    async def set_permissions(self, role, *, overwrite, reason=None):
        if self.error is not None:
            raise self.error
        self.calls.append((role.id, overwrite, reason))


class FakeGuild:
    def __init__(self, roles=(), channels=()):
        self.me = Member(1)
        self.default_role = FakeRole(0)
        self._roles = {r.id: r for r in roles}
        self._channels = {c.id: c for c in channels}

    def get_role(self, rid):
        return self._roles.get(rid)

    def get_channel(self, cid):
        return self._channels.get(cid)


def ticket(cid: int, *, closed=False, saved: dict | None = None):
    return SimpleNamespace(
        channel_id=cid,
        closed_at=CLOSED if closed else None,
        locked_overwrites_json=None if saved is None else json.dumps(saved),
    )


def forbidden():
    return discord.Forbidden(SimpleNamespace(status=403, reason="no"), "missing")


class TestPermissionIssues:
    def test_split_by_target(self):
        guild = FakeGuild()
        category = FakeChannel(1, manage_channels=False, manage_roles=True, manage_messages=False)
        lobby = FakeChannel(2, view_channel=True, send_messages=False, embed_links=False)
        assert [i.permission for i in category_permission_issues(guild, category)] == [
            "Manage Channels",
            "Manage Messages",
        ]
        assert [i.permission for i in lobby_channel_permission_issues(guild, lobby)] == [
            "Send Messages",
            "Embed Links",
        ]

    def test_missing_target_is_skipped(self):
        guild = FakeGuild()
        assert category_permission_issues(guild, None) == []
        assert lobby_channel_permission_issues(guild, None) == []


class FakeCategory:
    def __init__(self, guild, overwrites):
        self.guild = guild
        self.overwrites = overwrites


class TestBuildOverwrites:
    def test_copies_category_hides_everyone_and_opens_for_participants(self):
        manager, existing = FakeRole(10), FakeRole(20)
        guild = FakeGuild(roles=[manager, existing])
        creator, me = Member(7), Member(1)
        category = FakeCategory(guild, {existing: discord.PermissionOverwrite(view_channel=True)})
        lobby = SimpleNamespace(manager_role_ids=[10, 999])  # 999 已不存在

        result = build_ticket_overwrites(category, lobby, creator, me)  # pyright: ignore[reportArgumentType]

        assert result[guild.default_role] == discord.PermissionOverwrite(view_channel=False)
        assert result[existing] == discord.PermissionOverwrite(view_channel=True)
        assert result[manager] == open_overwrite()
        assert result[creator] == open_overwrite()
        assert result[me] == open_overwrite()
        assert len(result) == 5

    def test_without_manager_roles(self):
        guild = FakeGuild()
        creator, me = Member(7), Member(1)
        result = build_ticket_overwrites(FakeCategory(guild, {}), SimpleNamespace(manager_role_ids=[]), creator, me)  # pyright: ignore[reportArgumentType]
        assert set(result) == {guild.default_role, creator, me}

    def test_category_overwrites_not_mutated(self):
        guild = FakeGuild()
        original = {FakeRole(20): discord.PermissionOverwrite(view_channel=True)}
        category = FakeCategory(guild, original)
        build_ticket_overwrites(category, SimpleNamespace(manager_role_ids=[]), Member(7), Member(1))  # pyright: ignore[reportArgumentType]
        assert len(original) == 1


class TestApplyManagerRoleChanges:
    def test_added_open_and_locked(self):
        role = FakeRole(10)
        open_ch, locked_ch, legacy_ch = FakeChannel(1), FakeChannel(2), FakeChannel(3)
        guild = FakeGuild(roles=[role], channels=[open_ch, locked_ch, legacy_ch])
        tickets = [ticket(1), ticket(2, closed=True, saved={"member:7": True}), ticket(3, closed=True)]

        failures, updates = asyncio.run(apply_manager_role_changes(guild, tickets, [10], [], "原因"))

        assert failures == []
        assert open_ch.calls == [(10, open_overwrite(), "原因")]
        assert locked_ch.calls == [(10, locked_overwrite(), "原因")]
        assert legacy_ch.calls == [(10, locked_overwrite(), "原因")]
        # 有保存值的鎖定頻道記下新身分組，重開後才能發言；沒有保存值的（測試版資料）不動
        assert json.loads(updates[2]) == {"member:7": True, "role:10": True}
        assert 3 not in updates
        assert 1 not in updates

    def test_removed_deletes_overwrite_and_saved_key(self):
        role = FakeRole(10)
        ch = FakeChannel(2)
        guild = FakeGuild(roles=[role], channels=[ch])
        tickets = [ticket(2, closed=True, saved={"role:10": True, "role:20": True})]

        failures, updates = asyncio.run(apply_manager_role_changes(guild, tickets, [], [10], "原因"))

        assert failures == []
        assert ch.calls == [(10, None, "原因")]
        assert json.loads(updates[2]) == {"role:20": True}

    def test_missing_channel_or_role_is_skipped(self):
        guild = FakeGuild(roles=[FakeRole(10)], channels=[FakeChannel(1)])
        failures, updates = asyncio.run(apply_manager_role_changes(guild, [ticket(1), ticket(99)], [10, 11], [12], "r"))
        assert failures == []
        assert updates == {}
        assert [c[0] for c in guild.get_channel(1).calls] == [10]  # pyright: ignore[reportOptionalMemberAccess]

    def test_failure_is_listed_and_does_not_stop_others(self):
        guild = FakeGuild(roles=[FakeRole(10)], channels=[FakeChannel(1), FakeChannel(2)])
        guild.get_channel(1).error = forbidden()  # pyright: ignore[reportOptionalMemberAccess]
        failures, _ = asyncio.run(apply_manager_role_changes(guild, [ticket(1), ticket(2)], [10], [], "r"))
        assert [f.channel_id for f in failures] == [1]
        assert "權限" in failures[0].reason
        assert len(guild.get_channel(2).calls) == 1  # pyright: ignore[reportOptionalMemberAccess]

    def test_failure_does_not_write_json(self):
        guild = FakeGuild(roles=[FakeRole(10)], channels=[FakeChannel(2)])
        guild.get_channel(2).error = forbidden()  # pyright: ignore[reportOptionalMemberAccess]
        failures, updates = asyncio.run(
            apply_manager_role_changes(guild, [ticket(2, closed=True, saved={})], [10], [], "r")
        )
        assert len(failures) == 1
        assert updates == {}


class PartialChannel(FakeChannel):
    """第 n 次 set_permissions 之後開始失敗"""

    def __init__(self, cid, fail_after):
        super().__init__(cid)
        self.fail_after = fail_after

    async def set_permissions(self, role, *, overwrite, reason=None):
        if len(self.calls) >= self.fail_after:
            raise forbidden()
        await super().set_permissions(role, overwrite=overwrite, reason=reason)


class TestPartialSuccess:
    def test_successful_part_is_still_written_back(self):
        # 新增 10 成功、移除 20 失敗：10 的覆寫已經在 Discord 上，JSON 必須跟上
        guild = FakeGuild(roles=[FakeRole(10), FakeRole(20)], channels=[PartialChannel(2, fail_after=1)])
        t = ticket(2, closed=True, saved={"role:20": True})
        failures, updates = asyncio.run(apply_manager_role_changes(guild, [t], [10], [20], "r"))  # pyright: ignore[reportArgumentType]
        assert [f.channel_id for f in failures] == [2]
        assert json.loads(updates[2]) == {"role:20": True, "role:10": True}

    def test_removed_part_succeeds_before_added_fails(self):
        # 兩個都新增、第二個失敗：只有第一個寫進 JSON
        guild = FakeGuild(roles=[FakeRole(10), FakeRole(11)], channels=[PartialChannel(2, fail_after=1)])
        failures, updates = asyncio.run(
            apply_manager_role_changes(guild, [ticket(2, closed=True, saved={})], [10, 11], [], "r")  # pyright: ignore[reportArgumentType]
        )
        assert len(failures) == 1
        assert json.loads(updates[2]) == {"role:10": True}
