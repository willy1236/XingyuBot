"""P-04：私人頻道的鎖定、重開、刪除（`starDiscord/ticket_channel.py`、`starlib/tickets.py`、頻道內按鈕；假 Discord，真實 PostgreSQL）。"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import discord
import pytest
from sqlmodel import update
from test_identity import repo  # noqa: F401

from starDiscord import ticket_channel, ticket_lobby
from starDiscord.ticket_channel import (
    TicketActionError,
    delete_ticket,
    lock_ticket,
    member_ticket_actions,
    reopen_ticket,
    restore_ticket_views,
)
from starDiscord.uiElement.view import TicketActionButton, TicketChannelView, TicketDeleteConfirmView
from starlib import sclient
from starlib.database import TicketChannel, TicketChannelLobby
from starlib.tickets import allowed_ticket_actions, locked_overwrites, overwrite_key, reopened_overwrites

GUILD_ID = 8_800_000_000_004_001
OTHER_GUILD = 8_800_000_000_004_002
LOBBY = 8_800_000_000_004_011
CATEGORY = 8_800_000_000_004_021
TICKET, TICKET_2 = 8_800_000_000_004_031, 8_800_000_000_004_032
CONTROL = 8_800_000_000_004_041
ROLE_MANAGER, ROLE_OTHER, ROLE_CATEGORY = 8_800_000_000_004_051, 8_800_000_000_004_052, 8_800_000_000_004_053
CREATOR, MANAGER, ADMIN, STRANGER, UNCACHED = (
    8_800_000_000_004_061,
    8_800_000_000_004_062,
    8_800_000_000_004_063,
    8_800_000_000_004_064,
    8_800_000_000_004_065,
)
BOT = 8_800_000_000_004_099
CREATED = datetime(2026, 1, 1, tzinfo=UTC)

OPEN = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
LOCKED = discord.PermissionOverwrite(view_channel=True, send_messages=False, read_message_history=True)
HIDDEN = discord.PermissionOverwrite(view_channel=False)


def http_error(cls=discord.HTTPException, status=500):
    return cls(SimpleNamespace(status=status, reason="boom"), "boom")


class RawOverwrite:
    """`channel._overwrites` 的元素（py-cord 的 `_Overwrites`）。"""

    def __init__(self, tid: int, kind: int, overwrite: discord.PermissionOverwrite):
        allow, deny = overwrite.pair()
        self.id, self.type, self.allow, self.deny = tid, kind, allow.value, deny.value

    def is_role(self):
        return self.type == 0

    def is_member(self):
        return self.type == 1


class FakeRole:
    def __init__(self, rid: int):
        self.id = rid


class FakeMember:
    def __init__(self, uid: int, roles=(), manage_channels=False):
        self.id = uid
        self.name = f"user{uid}"
        self.mention = f"<@{uid}>"
        self.roles = [FakeRole(r) for r in roles]
        self.guild_permissions = SimpleNamespace(manage_channels=manage_channels)


class FakeMessage:
    def __init__(self, mid: int, custom_ids=()):
        self.id = mid
        self.components = [SimpleNamespace(children=[SimpleNamespace(custom_id=c) for c in custom_ids])]
        self.edits: list[dict] = []

    async def edit(self, **kwargs):
        self.edits.append(kwargs)


class FakeCategory:
    type = discord.ChannelType.category

    def __init__(self, guild):
        self.guild = guild
        self.id = CATEGORY
        self._overwrites = [
            RawOverwrite(ROLE_CATEGORY, 0, discord.PermissionOverwrite(view_channel=True, send_messages=False)),
            RawOverwrite(ROLE_OTHER, 0, discord.PermissionOverwrite(send_messages=True)),
        ]


class FakeTicketChannel:
    """py-cord 的行為：`edit`、`set_permissions` 只改 Discord 上的狀態（`truth`），不更新本地快取 `_overwrites`；
    快取要等 gateway 事件（`sync()`）。`guild.fetch_channel` 回一份帶最新覆寫的新物件。"""

    type = discord.ChannelType.text

    def __init__(self, guild, cid: int, overwrites: dict[tuple[str, int], discord.PermissionOverwrite]):
        self.guild = guild
        self.id = cid
        self.mention = f"<#{cid}>"
        self.category = guild.category
        self.set_overwrites(overwrites)
        self.edits: list[tuple[dict, str | None]] = []
        self.sent: list[str] = []
        self.deleted_reason: str | None = None
        self.messages: dict[int, FakeMessage] = {CONTROL: FakeMessage(CONTROL)}
        self.fail_edit: Exception | None = None
        self.fail_delete: Exception | None = None

    def set_overwrites(self, overwrites):
        """設定 Discord 上的覆寫並同步快取（測試的前置狀態）。"""
        self.truth = {"ows": [RawOverwrite(tid, 0 if kind == "role" else 1, o) for (kind, tid), o in overwrites.items()]}
        self.sync()

    def sync(self):
        """模擬 gateway 的 CHANNEL_UPDATE 到達：快取追上 Discord 上的狀態。"""
        self._overwrites = list(self.truth["ows"])

    def fetched(self):
        copy = object.__new__(FakeTicketChannel)
        copy.__dict__.update(self.__dict__)
        copy._overwrites = list(self.truth["ows"])
        return copy

    def state(self) -> dict[str, discord.PermissionOverwrite]:
        """Discord 上目前的覆寫：鍵 → 覆寫"""
        return {
            overwrite_key("role" if o.is_role() else "member", o.id): discord.PermissionOverwrite.from_pair(
                discord.Permissions(o.allow), discord.Permissions(o.deny)
            )
            for o in self.truth["ows"]
        }

    async def set_permissions(self, target, *, overwrite=None, reason=None):
        kind = 0 if target.id in self.guild.roles else 1
        rest = [o for o in self.truth["ows"] if o.id != target.id]
        self.truth["ows"] = rest if overwrite is None else [*rest, RawOverwrite(target.id, kind, overwrite)]

    def send_of(self, key: str):
        return self.state()[key].send_messages

    async def edit(self, *, overwrites, reason=None):
        # 讓並行的流程有機會交錯
        for _ in range(3):
            await asyncio.sleep(0)
        if self.fail_edit is not None:
            raise self.fail_edit
        self.edits.append((overwrites, reason))
        self.truth["ows"] = [RawOverwrite(t.id, 0 if t.id in self.guild.roles else 1, o) for t, o in overwrites.items()]

    async def send(self, text, **kwargs):
        self.sent.append(text)

    def get_partial_message(self, mid):
        return self.messages.setdefault(mid, FakeMessage(mid))

    async def fetch_message(self, mid):
        if mid not in self.messages:
            raise http_error(discord.NotFound, 404)
        return self.messages[mid]

    async def delete(self, *, reason=None):
        if self.fail_delete is not None:
            raise self.fail_delete
        self.deleted_reason = reason
        self.guild.channels.pop(self.id, None)


class FakeGuild:
    def __init__(self):
        self.id = GUILD_ID
        self.unavailable = False
        self.roles = {r: FakeRole(r) for r in (GUILD_ID, ROLE_MANAGER, ROLE_OTHER, ROLE_CATEGORY)}
        self.members = {
            uid: FakeMember(uid)
            for uid in (CREATOR, MANAGER, ADMIN, STRANGER, BOT)  # UNCACHED 不在成員快取
        }
        self.me = self.members[BOT]
        self.category = FakeCategory(self)
        self.channels: dict[int, object] = {CATEGORY: self.category}
        self.fail_fetch: Exception | None = None

    def get_channel(self, cid):
        return self.channels.get(cid)

    async def fetch_channel(self, cid):
        if self.fail_fetch is not None:
            raise self.fail_fetch
        channel = self.channels.get(cid)
        if not isinstance(channel, FakeTicketChannel):
            raise http_error(discord.NotFound, 404)
        return channel.fetched()

    def get_role(self, rid):
        return self.roles.get(rid)

    def get_member(self, uid):
        return self.members.get(uid)


def ticket_overwrites(bot=True, extra=None) -> dict:
    """P-03 開單後的覆寫：@everyone 看不到，分類覆寫的身分組、建立者、管理身分組、bot 能發言。"""
    ows = {
        ("role", GUILD_ID): HIDDEN,
        ("role", ROLE_CATEGORY): discord.PermissionOverwrite(view_channel=True),
        ("role", ROLE_MANAGER): OPEN,
        ("member", CREATOR): OPEN,
        ("member", UNCACHED): discord.PermissionOverwrite(view_channel=True, send_messages=None),
    }
    if bot:
        ows[("member", BOT)] = OPEN
    ows.update(extra or {})
    return ows


@pytest.fixture
def env(repo, monkeypatch):  # noqa: F811
    monkeypatch.setattr(ticket_channel, "sqldb", repo)
    monkeypatch.setattr(ticket_lobby, "sqldb", repo)
    # 鎖綁定第一次等待時的事件迴圈；每個測試用自己的迴圈
    monkeypatch.setattr(ticket_channel, "_locks", {})
    monkeypatch.setattr(ticket_lobby, "_locks", {})
    monkeypatch.setattr(ticket_channel, "_messages_refreshed", False)
    views: list[tuple[int | None, discord.ui.View]] = []
    monkeypatch.setattr(sclient, "bot", SimpleNamespace(add_view=lambda v, message_id=None: views.append((message_id, v))))
    guild = FakeGuild()
    repo.merge(
        TicketChannelLobby(
            channel_id=LOBBY, category_id=1, guild_id=GUILD_ID, message_id=1, ticket_category_id=CATEGORY
        )
    )
    repo.set_lobby_manager_roles(LOBBY, [ROLE_MANAGER])
    return SimpleNamespace(guild=guild, repo=repo, views=views)


def add_ticket(env, cid=TICKET, *, closed=False, saved=None, lobby=LOBBY, overwrites=None, guild_id=GUILD_ID):
    env.repo.merge(
        TicketChannel(
            channel_id=cid,
            guild_id=guild_id,
            creator_id=CREATOR,
            created_at=CREATED,
            closed_at=CREATED if closed else None,
            closer_id=ADMIN if closed else None,
            view_message_id=CONTROL,
            lobby_channel_id=lobby,
            locked_overwrites_json=json.dumps(saved) if saved is not None else None,
        )
    )
    channel = FakeTicketChannel(env.guild, cid, overwrites if overwrites is not None else ticket_overwrites())
    env.guild.channels[cid] = channel
    return channel


def snap(env, cid=TICKET):
    return env.repo.get_ticket_snapshot(cid)


def member(env, uid, roles=(), manage_channels=False):
    m = FakeMember(uid, roles, manage_channels)
    env.guild.members[uid] = m
    return m


def run(coro):
    return asyncio.run(coro)


def custom_ids(view: discord.ui.View) -> list[str]:
    return [item.custom_id for item in view.children]  # pyright: ignore[reportAttributeAccessIssue]


# ====== 權限對照表 ======


@pytest.mark.parametrize(
    ("creator", "manager", "manage_channels", "expected"),
    [
        (True, False, False, {"lock"}),
        (False, True, False, {"lock", "reopen", "delete"}),
        (False, False, True, {"lock", "reopen", "delete"}),
        (True, True, False, {"lock", "reopen", "delete"}),
        (False, False, False, set()),
    ],
)
def test_allowed_actions_table(creator, manager, manage_channels, expected):
    assert allowed_ticket_actions(is_creator=creator, is_manager=manager, manage_channels=manage_channels) == expected


class TestMemberActions:
    def test_creator_can_only_lock(self, env):
        add_ticket(env)
        assert member_ticket_actions(env.guild, TICKET, member(env, CREATOR)) == {"lock"}

    def test_manager_role_can_do_all(self, env):
        add_ticket(env)
        assert member_ticket_actions(env.guild, TICKET, member(env, MANAGER, [ROLE_MANAGER])) == {"lock", "reopen", "delete"}

    def test_manage_channels_can_do_all(self, env):
        add_ticket(env)
        assert member_ticket_actions(env.guild, TICKET, member(env, ADMIN, manage_channels=True)) == {"lock", "reopen", "delete"}

    def test_others_can_do_nothing(self, env):
        add_ticket(env)
        assert member_ticket_actions(env.guild, TICKET, member(env, STRANGER, [ROLE_OTHER])) == set()

    def test_manager_of_another_lobby_does_not_count(self, env):
        add_ticket(env)
        env.repo.set_lobby_manager_roles(LOBBY, [ROLE_OTHER])
        assert member_ticket_actions(env.guild, TICKET, member(env, MANAGER, [ROLE_MANAGER])) == set()

    def test_removed_lobby_leaves_only_manage_channels(self, env):
        add_ticket(env)
        env.repo.remove_ticket_lobby(LOBBY)  # 底下的頻道改為未歸屬
        assert member_ticket_actions(env.guild, TICKET, member(env, MANAGER, [ROLE_MANAGER])) == set()
        assert member_ticket_actions(env.guild, TICKET, member(env, CREATOR)) == set()
        assert member_ticket_actions(env.guild, TICKET, member(env, ADMIN, manage_channels=True)) == {"lock", "reopen", "delete"}

    def test_removed_lobby_still_referenced_does_not_count(self, env):
        """紀錄仍指向已移除的大廳（例如移除後才寫入的資料）時，同樣只剩 Manage Channels。"""
        add_ticket(env)
        env.repo.session.exec(update(TicketChannelLobby).where(TicketChannelLobby.channel_id == LOBBY).values(removed_at=CREATED))
        env.repo.session.commit()
        assert member_ticket_actions(env.guild, TICKET, member(env, MANAGER, [ROLE_MANAGER])) == set()
        assert member_ticket_actions(env.guild, TICKET, member(env, CREATOR)) == set()

    def test_unassigned_only_manage_channels(self, env):
        add_ticket(env, lobby=None)
        assert member_ticket_actions(env.guild, TICKET, member(env, CREATOR)) == set()
        assert member_ticket_actions(env.guild, TICKET, member(env, ADMIN, manage_channels=True)) == {"lock", "reopen", "delete"}


# ====== 覆寫計算 ======


class TestOverwriteRules:
    def test_lock_mutes_everyone_but_bot_and_keeps_other_perms(self, env):
        channel = add_ticket(env)
        overwrites, saved = locked_overwrites(channel, env.guild.me)
        by_id = {t.id: o for t, o in overwrites.items()}
        for tid in (GUILD_ID, ROLE_CATEGORY, ROLE_MANAGER, CREATOR, UNCACHED):
            assert by_id[tid].send_messages is False
        assert by_id[BOT].send_messages is True
        assert by_id[GUILD_ID].view_channel is False
        assert by_id[ROLE_MANAGER].view_channel is True and by_id[ROLE_MANAGER].read_message_history is True
        assert saved == {
            f"role:{GUILD_ID}": None,
            f"role:{ROLE_CATEGORY}": None,
            f"role:{ROLE_MANAGER}": True,
            f"member:{CREATOR}": True,
            f"member:{UNCACHED}": None,
        }

    def test_uncached_member_is_kept_as_member_object(self, env):
        channel = add_ticket(env)
        overwrites, _ = locked_overwrites(channel, env.guild.me)
        [uncached] = [t for t in overwrites if t.id == UNCACHED]
        assert isinstance(uncached, discord.Object)

    def test_bot_without_overwrite_gets_one(self, env):
        channel = add_ticket(env, overwrites=ticket_overwrites(bot=False))
        overwrites, saved = locked_overwrites(channel, env.guild.me)
        assert overwrites[env.guild.me].send_messages is True
        assert f"member:{BOT}" not in saved

    def test_reopen_restores_saved_and_keeps_later_targets(self, env):
        channel = add_ticket(env, overwrites={("role", ROLE_MANAGER): LOCKED, ("role", ROLE_OTHER): LOCKED, ("member", BOT): OPEN})
        result = reopened_overwrites(channel, env.guild.me, {f"role:{ROLE_MANAGER}": None}, creator_id=CREATOR, manager_role_ids=[])
        by_id = {t.id: o for t, o in result.items()}
        assert by_id[ROLE_MANAGER].send_messages is None
        assert by_id[ROLE_OTHER].send_messages is False  # 鎖定後才加上，沒有保存值：不動
        assert by_id[BOT].send_messages is True


# ====== 鎖定 ======


class TestLock:
    def test_lock_saves_and_switches_buttons(self, env):
        channel = add_ticket(env)
        actor = member(env, CREATOR)
        state = run(lock_ticket(env.guild, TICKET, actor, "reason-lock"))

        assert (state.status, state.changed) == ("locked", True)
        for key in (f"role:{GUILD_ID}", f"role:{ROLE_MANAGER}", f"member:{CREATOR}", f"member:{UNCACHED}"):
            assert channel.send_of(key) is False
        assert channel.send_of(f"member:{BOT}") is True
        assert channel.edits[0][1] == "reason-lock"
        s = snap(env)
        assert s["closed_at"] is not None and s["closer_id"] == CREATOR
        assert json.loads(s["locked_overwrites_json"])[f"role:{ROLE_MANAGER}"] is True
        [edit] = channel.messages[CONTROL].edits
        assert custom_ids(edit["view"]) == [f"ticket_reopen_{TICKET}", f"ticket_delete_{TICKET}"]
        assert any("鎖定" in t for t in channel.sent)

    def test_already_locked_is_success_without_changes(self, env):
        channel = add_ticket(env, closed=True, saved={})
        state = run(lock_ticket(env.guild, TICKET, member(env, ADMIN), "r"))
        assert (state.status, state.changed) == ("locked", False)
        assert channel.edits == [] and snap(env)["closer_id"] == ADMIN

    def test_not_found_and_other_guild(self, env):
        with pytest.raises(TicketActionError) as e:
            run(lock_ticket(env.guild, TICKET, member(env, ADMIN), "r"))
        assert e.value.code == "not_found"
        add_ticket(env, guild_id=OTHER_GUILD)
        with pytest.raises(TicketActionError) as e:
            run(lock_ticket(env.guild, TICKET, member(env, ADMIN), "r"))
        assert e.value.code == "not_found"

    def test_channel_deleted_in_discord_removes_record(self, env):
        add_ticket(env)
        env.guild.channels.pop(TICKET)
        with pytest.raises(TicketActionError) as e:
            run(lock_ticket(env.guild, TICKET, member(env, ADMIN), "r"))
        assert e.value.code == "channel_gone"
        assert snap(env) is None

    def test_forbidden_changes_nothing(self, env):
        channel = add_ticket(env)
        channel.fail_edit = http_error(discord.Forbidden, 403)
        with pytest.raises(TicketActionError) as e:
            run(lock_ticket(env.guild, TICKET, member(env, ADMIN), "r"))
        assert e.value.code == "bot_missing_permission"
        assert snap(env)["closed_at"] is None

    def test_other_discord_error(self, env):
        channel = add_ticket(env)
        channel.fail_edit = http_error()
        with pytest.raises(TicketActionError) as e:
            run(lock_ticket(env.guild, TICKET, member(env, ADMIN), "r"))
        assert (e.value.code, e.value.message) == ("discord_error", "boom")

    def test_db_failure_restores_overwrites(self, env, monkeypatch):
        channel = add_ticket(env)
        before = channel.state()

        def boom(*a, **k):
            raise RuntimeError("db down")

        monkeypatch.setattr(env.repo, "lock_ticket_record", boom)
        with pytest.raises(TicketActionError) as e:
            run(lock_ticket(env.guild, TICKET, member(env, ADMIN), "r"))
        assert e.value.code == "save_failed"
        assert channel.state() == before

    def test_control_message_gone_still_locks(self, env):
        channel = add_ticket(env)

        async def gone(**kwargs):
            raise http_error(discord.NotFound, 404)

        channel.messages[CONTROL].edit = gone
        state = run(lock_ticket(env.guild, TICKET, member(env, ADMIN), "r"))
        assert state.changed and snap(env)["closed_at"] is not None


# ====== 重開 ======


class TestReopen:
    def lock_then_reopen(self, env, channel):
        run(lock_ticket(env.guild, TICKET, member(env, CREATOR), "r"))
        return run(reopen_ticket(env.guild, TICKET, member(env, MANAGER, [ROLE_MANAGER]), "reason-reopen"))

    def test_reopen_restores_pre_lock_send_and_clears(self, env):
        channel = add_ticket(env)
        before = channel.state()
        state = self.lock_then_reopen(env, channel)

        assert (state.status, state.changed) == ("open", True)
        assert channel.state() == before
        assert channel.edits[-1][1] == "reason-reopen"
        s = snap(env)
        assert (s["closed_at"], s["closer_id"], s["locked_overwrites_json"]) == (None, None, None)
        assert custom_ids(channel.messages[CONTROL].edits[-1]["view"]) == [f"ticket_lock_{TICKET}"]

    def test_manager_role_added_while_locked_can_speak_after_reopen(self, env):
        """P-02 在鎖定中加入管理身分組：覆寫只給查看，`locked_overwrites_json` 記 true。"""
        channel = add_ticket(env)
        run(lock_ticket(env.guild, TICKET, member(env, CREATOR), "r"))
        state = channel.state()
        state[f"role:{ROLE_OTHER}"] = LOCKED
        channel.set_overwrites({(k.split(":")[0], int(k.split(":")[1])): o for k, o in state.items()})
        saved = json.loads(snap(env)["locked_overwrites_json"])
        saved[f"role:{ROLE_OTHER}"] = True
        env.repo.set_ticket_locked_overwrites({TICKET: json.dumps(saved)})

        run(reopen_ticket(env.guild, TICKET, member(env, ADMIN, manage_channels=True), "r"))
        assert channel.send_of(f"role:{ROLE_OTHER}") is True

    def test_already_open_is_success_without_changes(self, env):
        channel = add_ticket(env)
        state = run(reopen_ticket(env.guild, TICKET, member(env, ADMIN), "r"))
        assert (state.status, state.changed) == ("open", False)
        assert channel.edits == []

    def test_legacy_lock_without_saved_uses_default_rule(self, env):
        """測試版鎖定：全部覆寫（含 bot）send=False，沒有保存值。"""
        legacy = {
            ("role", GUILD_ID): discord.PermissionOverwrite(view_channel=False, send_messages=False),
            ("role", ROLE_CATEGORY): discord.PermissionOverwrite(view_channel=True, send_messages=False),
            ("role", ROLE_OTHER): discord.PermissionOverwrite(view_channel=True, send_messages=False),
            ("role", ROLE_MANAGER): LOCKED,
            ("member", CREATOR): LOCKED,
            ("member", BOT): LOCKED,
            ("member", STRANGER): LOCKED,
        }
        channel = add_ticket(env, closed=True, overwrites=legacy)
        run(reopen_ticket(env.guild, TICKET, member(env, ADMIN, manage_channels=True), "r"))

        assert channel.send_of(f"member:{CREATOR}") is True
        assert channel.send_of(f"role:{ROLE_MANAGER}") is True
        assert channel.send_of(f"member:{BOT}") is True
        # 其餘回到分類的覆寫：分類對 ROLE_CATEGORY 設 False、ROLE_OTHER 設 True，其他沒設
        assert channel.send_of(f"role:{ROLE_CATEGORY}") is False
        assert channel.send_of(f"role:{ROLE_OTHER}") is True
        assert channel.send_of(f"role:{GUILD_ID}") is None
        assert channel.send_of(f"member:{STRANGER}") is None
        # 其他權限不動
        assert channel.state()[f"role:{GUILD_ID}"].view_channel is False
        assert snap(env)["closed_at"] is None

    def test_legacy_lock_in_removed_lobby_does_not_restore_managers(self, env):
        channel = add_ticket(env, closed=True, overwrites={("role", ROLE_MANAGER): LOCKED, ("member", CREATOR): LOCKED})
        env.repo.remove_ticket_lobby(LOBBY)
        run(reopen_ticket(env.guild, TICKET, member(env, ADMIN, manage_channels=True), "r"))
        assert channel.send_of(f"role:{ROLE_MANAGER}") is None
        assert channel.send_of(f"member:{CREATOR}") is True

    def test_invalid_json_falls_back_to_default_rule(self, env):
        channel = add_ticket(env, closed=True, overwrites={("member", CREATOR): LOCKED})
        env.repo.set_ticket_locked_overwrites({TICKET: "not json"})
        run(reopen_ticket(env.guild, TICKET, member(env, ADMIN), "r"))
        assert channel.send_of(f"member:{CREATOR}") is True

    def test_db_failure_restores_overwrites(self, env, monkeypatch):
        channel = add_ticket(env, closed=True, saved={f"member:{CREATOR}": True}, overwrites={("member", CREATOR): LOCKED})
        monkeypatch.setattr(env.repo, "reopen_ticket_record", lambda *a: False)
        with pytest.raises(TicketActionError) as e:
            run(reopen_ticket(env.guild, TICKET, member(env, ADMIN), "r"))
        assert e.value.code == "save_failed"
        assert channel.send_of(f"member:{CREATOR}") is False

    def test_channel_gone(self, env):
        add_ticket(env, closed=True)
        env.guild.channels.pop(TICKET)
        with pytest.raises(TicketActionError) as e:
            run(reopen_ticket(env.guild, TICKET, member(env, ADMIN), "r"))
        assert e.value.code == "channel_gone"


# ====== 刪除 ======


class TestDelete:
    def test_delete_channel_and_record(self, env):
        channel = add_ticket(env, closed=True)
        state = run(delete_ticket(env.guild, TICKET, "reason-delete"))
        assert (state.status, state.changed) == ("deleted", True)
        assert channel.deleted_reason == "reason-delete"
        assert snap(env) is None and TICKET not in env.guild.channels

    def test_open_channel_can_be_deleted(self, env):
        add_ticket(env)
        assert run(delete_ticket(env.guild, TICKET, "r")).changed

    def test_no_record_is_success_and_touches_nothing(self, env):
        stray = FakeTicketChannel(env.guild, TICKET_2, {})
        env.guild.channels[TICKET_2] = stray
        state = run(delete_ticket(env.guild, TICKET_2, "r"))
        assert (state.status, state.changed) == ("deleted", False)
        assert TICKET_2 in env.guild.channels

    def test_other_guild_record_is_not_deleted(self, env):
        add_ticket(env, guild_id=OTHER_GUILD)
        assert not run(delete_ticket(env.guild, TICKET, "r")).changed
        assert TICKET in env.guild.channels and snap(env) is not None

    def test_already_deleted_in_discord(self, env):
        add_ticket(env)
        env.guild.channels.pop(TICKET)
        state = run(delete_ticket(env.guild, TICKET, "r"))
        assert (state.status, state.changed) == ("deleted", False)
        assert snap(env) is None

    def test_not_found_while_deleting_is_success(self, env):
        channel = add_ticket(env)
        channel.fail_delete = http_error(discord.NotFound, 404)
        assert run(delete_ticket(env.guild, TICKET, "r")).changed
        assert snap(env) is None

    def test_forbidden_keeps_record(self, env):
        channel = add_ticket(env)
        channel.fail_delete = http_error(discord.Forbidden, 403)
        with pytest.raises(TicketActionError) as e:
            run(delete_ticket(env.guild, TICKET, "r"))
        assert e.value.code == "bot_missing_permission"
        assert snap(env) is not None


# ====== 並行 ======


class TestConcurrency:
    def test_two_locks_at_once_keep_the_real_pre_lock_values(self, env):
        """沒有每頻道的鎖時，第二個鎖定會把已被改成 False 的覆寫存成「鎖定前」，重開後永遠不能發言。"""
        channel = add_ticket(env)
        before = channel.state()

        async def both():
            return await asyncio.gather(
                lock_ticket(env.guild, TICKET, member(env, CREATOR), "a"),
                lock_ticket(env.guild, TICKET, member(env, ADMIN), "b"),
            )

        results = run(both())
        assert sorted(r.changed for r in results) == [False, True]
        assert len(channel.edits) == 1
        run(reopen_ticket(env.guild, TICKET, member(env, ADMIN), "r"))
        assert channel.state() == before

    def test_lock_and_reopen_do_not_interleave(self, env):
        channel = add_ticket(env)
        before = channel.state()

        async def both():
            lock = asyncio.create_task(lock_ticket(env.guild, TICKET, member(env, CREATOR), "a"))
            await asyncio.sleep(0)
            reopen = asyncio.create_task(reopen_ticket(env.guild, TICKET, member(env, ADMIN), "b"))
            return await lock, await reopen

        locked, reopened = run(both())
        assert locked.changed and reopened.changed
        assert channel.state() == before and snap(env)["closed_at"] is None

    def test_waits_for_the_lobby_lock(self, env):
        """大廳修改套用管理身分組時持有 lobby_lock，鎖定要等它做完才動覆寫。"""
        channel = add_ticket(env)
        edits_while_held: list[int] = []

        async def scenario():
            async with ticket_lobby.lobby_lock(LOBBY):
                task = asyncio.create_task(lock_ticket(env.guild, TICKET, member(env, ADMIN), "r"))
                for _ in range(20):
                    await asyncio.sleep(0)
                edits_while_held.append(len(channel.edits))
            await task

        run(scenario())
        assert edits_while_held == [0]
        assert len(channel.edits) == 1


# ====== 按鈕 ======


class FakeResponse:
    def __init__(self):
        self.messages: list[tuple[str, dict]] = []
        self.deferred = None
        self.edited = None

    async def send_message(self, content=None, **kwargs):
        self.messages.append((content, kwargs))

    async def defer(self, **kwargs):
        self.deferred = kwargs

    async def edit_message(self, **kwargs):
        self.edited = kwargs

    def is_done(self):
        return bool(self.messages) or self.deferred is not None or self.edited is not None


class FakeFollowup:
    def __init__(self):
        self.messages: list[tuple[str, dict]] = []

    async def send(self, content=None, **kwargs):
        self.messages.append((content, kwargs))


def interaction(env, user):
    return SimpleNamespace(guild=env.guild, user=user, channel_id=TICKET, response=FakeResponse(), followup=FakeFollowup())


def patch_member_type(monkeypatch):
    """按鈕只接受 discord.Member；讓假成員通過檢查。"""
    import starDiscord.uiElement.view as view_module

    monkeypatch.setattr(view_module.discord, "Member", FakeMember)


class TestButtons:
    def test_view_states(self):
        async def build():
            return TicketChannelView(TICKET, False), TicketChannelView(TICKET, True)

        open_view, locked_view = run(build())
        assert custom_ids(open_view) == [f"ticket_lock_{TICKET}"]
        assert custom_ids(locked_view) == [f"ticket_reopen_{TICKET}", f"ticket_delete_{TICKET}"]
        assert open_view.timeout is None and locked_view.timeout is None

    @pytest.mark.parametrize("action", ["reopen", "delete"])
    def test_creator_cannot_reopen_or_delete(self, env, monkeypatch, action):
        patch_member_type(monkeypatch)
        add_ticket(env, closed=True, saved={})
        inter = interaction(env, member(env, CREATOR))
        run(TicketActionButton(action, TICKET).callback(inter))
        [(text, kwargs)] = inter.response.messages
        assert kwargs["ephemeral"] is True and "只有" in text
        assert snap(env)["closed_at"] is not None and TICKET in env.guild.channels

    def test_stranger_cannot_lock(self, env, monkeypatch):
        patch_member_type(monkeypatch)
        add_ticket(env)
        inter = interaction(env, member(env, STRANGER))
        run(TicketActionButton("lock", TICKET).callback(inter))
        assert inter.response.messages[0][1]["ephemeral"] is True
        assert snap(env)["closed_at"] is None

    def test_creator_locks_then_manager_reopens(self, env, monkeypatch):
        patch_member_type(monkeypatch)
        channel = add_ticket(env)
        inter = interaction(env, member(env, CREATOR))
        run(TicketActionButton("lock", TICKET).callback(inter))
        assert inter.response.deferred == {"ephemeral": True}
        assert inter.followup.messages[0][1]["ephemeral"] is True
        assert channel.send_of(f"member:{CREATOR}") is False and channel.send_of(f"role:{ROLE_MANAGER}") is False
        assert channel.send_of(f"member:{BOT}") is True
        # 不經後台：稽核原因沒有「透過後台」
        assert "透過後台" not in channel.edits[0][1]

        inter = interaction(env, member(env, MANAGER, [ROLE_MANAGER]))
        run(TicketActionButton("reopen", TICKET).callback(inter))
        assert channel.send_of(f"member:{CREATOR}") is True and channel.send_of(f"role:{ROLE_MANAGER}") is True

    def test_removed_lobby_manager_is_refused_admin_is_not(self, env, monkeypatch):
        patch_member_type(monkeypatch)
        add_ticket(env)
        env.repo.remove_ticket_lobby(LOBBY)
        for action in ("lock",):
            inter = interaction(env, member(env, MANAGER, [ROLE_MANAGER]))
            run(TicketActionButton(action, TICKET).callback(inter))
            assert inter.response.messages and snap(env)["closed_at"] is None
        inter = interaction(env, member(env, ADMIN, manage_channels=True))
        run(TicketActionButton("lock", TICKET).callback(inter))
        assert snap(env)["closed_at"] is not None

    def test_delete_asks_for_confirmation_then_deletes(self, env, monkeypatch):
        patch_member_type(monkeypatch)
        add_ticket(env, closed=True, saved={})
        manager = member(env, MANAGER, [ROLE_MANAGER])
        inter = interaction(env, manager)
        run(TicketActionButton("delete", TICKET).callback(inter))
        [(text, kwargs)] = inter.response.messages
        assert "無法復原" in text and kwargs["ephemeral"] is True
        confirm_view = kwargs["view"]
        assert isinstance(confirm_view, TicketDeleteConfirmView)
        assert TICKET in env.guild.channels

        inter = interaction(env, manager)
        run(confirm_view.children[0].callback(inter))  # pyright: ignore[reportAttributeAccessIssue]
        assert TICKET not in env.guild.channels and snap(env) is None


# ====== 啟動載入與置頂訊息更新 ======


class TestRestoreViews:
    def bot(self, env):
        views: list = []
        return SimpleNamespace(
            get_channel=env.guild.get_channel, add_view=lambda v, message_id=None: views.append((message_id, v)), views=views
        )

    def test_loads_open_and_locked_and_upgrades_old_buttons_once(self, env):
        open_ch = add_ticket(env, TICKET)
        open_ch.messages[CONTROL] = FakeMessage(CONTROL, [f"close_ticket_channel_{TICKET}"])
        locked_ch = add_ticket(env, TICKET_2, closed=True)
        locked_ch.messages[CONTROL] = FakeMessage(CONTROL, [f"ticket_reopen_{TICKET_2}", f"ticket_delete_{TICKET_2}"])
        bot = self.bot(env)
        run(restore_ticket_views(bot))

        loaded = {custom_ids(v)[0]: mid for mid, v in bot.views}
        assert loaded == {f"ticket_lock_{TICKET}": CONTROL, f"ticket_reopen_{TICKET_2}": CONTROL}
        [edit] = open_ch.messages[CONTROL].edits
        assert custom_ids(edit["view"]) == [f"ticket_lock_{TICKET}"]
        assert locked_ch.messages[CONTROL].edits == []  # 已是新按鈕，不再更新

    def test_legacy_locked_channel_without_buttons_gets_reopen_and_delete(self, env):
        channel = add_ticket(env, closed=True)
        channel.messages[CONTROL] = FakeMessage(CONTROL)  # 測試版鎖定時清空了按鈕
        run(restore_ticket_views(self.bot(env)))
        assert custom_ids(channel.messages[CONTROL].edits[0]["view"]) == [f"ticket_reopen_{TICKET}", f"ticket_delete_{TICKET}"]

    def test_missing_message_or_channel_is_skipped(self, env):
        channel = add_ticket(env)
        channel.messages.clear()
        add_ticket(env, TICKET_2)
        env.guild.channels.pop(TICKET_2)
        bot = self.bot(env)
        run(restore_ticket_views(bot))
        assert [mid for mid, _ in bot.views] == [CONTROL]


# ====== repository ======


class TestRepository:
    def test_lock_and_reopen_records_are_conditional(self, env):
        add_ticket(env)
        assert env.repo.lock_ticket_record(TICKET, ADMIN, CREATED, "{}")
        assert not env.repo.lock_ticket_record(TICKET, CREATOR, CREATED, "{}")
        assert snap(env)["closer_id"] == ADMIN
        assert env.repo.reopen_ticket_record(TICKET)
        assert not env.repo.reopen_ticket_record(TICKET)
        assert not env.repo.lock_ticket_record(TICKET_2, ADMIN, CREATED, "{}")

    def test_list_all_includes_locked(self, env):
        add_ticket(env, TICKET)
        add_ticket(env, TICKET_2, closed=True)
        ids = {t.channel_id for t in env.repo.list_all_ticket_channels()}
        assert {TICKET, TICKET_2} <= ids


# ====== 快取延遲（覆寫快取要等 gateway 事件才更新） ======


class TestStaleCache:
    """鎖定、重開前向 Discord 讀最新覆寫；改回讀快取時這些測試會失敗。"""

    def apply(self, env, added=(), removed=()):
        from starlib.tickets import apply_manager_role_changes

        t = SimpleNamespace(channel_id=TICKET, closed_at=None, locked_overwrites_json=None)
        failures, _ = run(apply_manager_role_changes(env.guild, [t], list(added), list(removed), "p02"))
        assert failures == []

    def test_lock_right_after_manager_role_removed(self, env):
        channel = add_ticket(env)
        self.apply(env, removed=[ROLE_MANAGER])  # 快取裡仍有 ROLE_MANAGER
        run(lock_ticket(env.guild, TICKET, member(env, ADMIN), "r"))
        assert f"role:{ROLE_MANAGER}" not in channel.state()
        assert f"role:{ROLE_MANAGER}" not in json.loads(snap(env)["locked_overwrites_json"])

    def test_lock_right_after_manager_role_added(self, env):
        channel = add_ticket(env)
        self.apply(env, added=[ROLE_OTHER])  # 快取裡還沒有 ROLE_OTHER
        run(lock_ticket(env.guild, TICKET, member(env, ADMIN), "r"))
        ow = channel.state()[f"role:{ROLE_OTHER}"]
        assert (ow.view_channel, ow.send_messages) == (True, False)
        assert json.loads(snap(env)["locked_overwrites_json"])[f"role:{ROLE_OTHER}"] is True

    def test_lock_right_after_reopen_keeps_pre_lock_values(self, env):
        channel = add_ticket(env)
        before = channel.state()
        admin = member(env, ADMIN)
        run(lock_ticket(env.guild, TICKET, admin, "r"))
        run(reopen_ticket(env.guild, TICKET, admin, "r"))
        run(lock_ticket(env.guild, TICKET, admin, "r"))  # 快取還停在第一次鎖定前
        assert json.loads(snap(env)["locked_overwrites_json"])[f"member:{CREATOR}"] is True
        run(reopen_ticket(env.guild, TICKET, admin, "r"))
        assert channel.state() == before

    def test_restore_uses_the_fresh_overwrites(self, env, monkeypatch):
        channel = add_ticket(env)
        self.apply(env, added=[ROLE_OTHER])
        fresh = channel.state()
        monkeypatch.setattr(env.repo, "lock_ticket_record", lambda *a: False)
        with pytest.raises(TicketActionError):
            run(lock_ticket(env.guild, TICKET, member(env, ADMIN), "r"))
        assert channel.state() == fresh

    def test_fetch_not_found_removes_record(self, env):
        add_ticket(env)
        env.guild.fail_fetch = http_error(discord.NotFound, 404)
        with pytest.raises(TicketActionError) as e:
            run(lock_ticket(env.guild, TICKET, member(env, ADMIN), "r"))
        assert e.value.code == "channel_gone" and snap(env) is None

    def test_fetch_forbidden(self, env):
        add_ticket(env)
        env.guild.fail_fetch = http_error(discord.Forbidden, 403)
        with pytest.raises(TicketActionError) as e:
            run(lock_ticket(env.guild, TICKET, member(env, ADMIN), "r"))
        assert e.value.code == "bot_missing_permission" and snap(env)["closed_at"] is None


# ====== 非預期錯誤與格式錯誤的保存值 ======


class TestUnexpectedErrors:
    @pytest.mark.parametrize("raw", ['{"role:1": "x"}', '{"role:1": 1}', "[true]", '"x"'])
    def test_wrong_value_types_fall_back_to_default_rule(self, env, raw):
        from starlib.tickets import parse_locked_overwrites

        assert parse_locked_overwrites(raw) is None
        channel = add_ticket(env, closed=True, overwrites={("member", CREATOR): LOCKED})
        env.repo.set_ticket_locked_overwrites({TICKET: raw})
        run(reopen_ticket(env.guild, TICKET, member(env, ADMIN), "r"))
        assert channel.send_of(f"member:{CREATOR}") is True

    def test_valid_values_are_kept(self):
        from starlib.tickets import parse_locked_overwrites

        assert parse_locked_overwrites('{"role:1": true, "role:2": false, "member:3": null}') == {
            "role:1": True,
            "role:2": False,
            "member:3": None,
        }

    def test_db_read_failure_becomes_failed(self, env, monkeypatch):
        add_ticket(env)

        def boom(*a):
            raise RuntimeError("db down")

        monkeypatch.setattr(env.repo, "get_ticket_snapshot", boom)
        with pytest.raises(TicketActionError) as e:
            run(lock_ticket(env.guild, TICKET, member(env, ADMIN), "r"))
        assert e.value.code == "failed"

    def test_button_replies_on_unexpected_error(self, env, monkeypatch):
        patch_member_type(monkeypatch)
        add_ticket(env)
        inter = interaction(env, member(env, ADMIN, manage_channels=True))

        async def boom(*a, **k):
            raise RuntimeError("unexpected")

        monkeypatch.setattr(ticket_channel, "lock_ticket", boom)
        run(TicketActionButton("lock", TICKET).callback(inter))
        [(text, kwargs)] = inter.followup.messages
        assert "操作失敗" in text and kwargs["ephemeral"] is True

    def test_button_replies_when_permission_check_fails(self, env, monkeypatch):
        patch_member_type(monkeypatch)
        add_ticket(env)
        inter = interaction(env, member(env, ADMIN, manage_channels=True))

        def boom(*a):
            raise RuntimeError("db down")

        monkeypatch.setattr(env.repo, "get_ticket_snapshot", boom)
        run(TicketActionButton("lock", TICKET).callback(inter))
        [(text, kwargs)] = inter.response.messages
        assert "操作失敗" in text and kwargs["ephemeral"] is True


# ====== 鎖內重新檢查權限 ======


class TestRecheckInsideLock:
    def test_creator_refused_when_lobby_removed_while_waiting(self, env):
        add_ticket(env)
        creator = member(env, CREATOR)

        async def scenario():
            async with ticket_lobby.lobby_lock(LOBBY):
                task = asyncio.create_task(lock_ticket(env.guild, TICKET, creator, "r", check_member=True))
                for _ in range(5):
                    await asyncio.sleep(0)
                env.repo.remove_ticket_lobby(LOBBY)
            return await asyncio.gather(task, return_exceptions=True)

        [result] = run(scenario())
        assert isinstance(result, TicketActionError) and result.code == "forbidden"
        assert snap(env)["closed_at"] is None

    def test_dashboard_call_does_not_check_member(self, env):
        add_ticket(env, lobby=None)
        # 後台的權限由區塊權限判斷；操作者不必有 Discord 內按鈕的權限
        assert run(lock_ticket(env.guild, TICKET, member(env, STRANGER), "r")).changed

    def test_delete_rechecks_member(self, env):
        add_ticket(env, closed=True, saved={})
        with pytest.raises(TicketActionError) as e:
            run(delete_ticket(env.guild, TICKET, "r", member=member(env, CREATOR)))
        assert e.value.code == "forbidden" and TICKET in env.guild.channels


class TestRestoreOnReconnect:
    def test_second_ready_only_registers_views(self, env):
        channel = add_ticket(env)
        channel.messages[CONTROL] = FakeMessage(CONTROL, [f"close_ticket_channel_{TICKET}"])
        calls: list[int] = []
        original = channel.fetch_message

        async def counting(mid):
            calls.append(mid)
            return await original(mid)

        channel.fetch_message = counting
        views: list = []
        bot = SimpleNamespace(get_channel=env.guild.get_channel, add_view=lambda v, message_id=None: views.append(message_id))
        run(restore_ticket_views(bot))
        run(restore_ticket_views(bot))
        assert calls == [CONTROL] and views == [CONTROL, CONTROL]

    def test_unexpected_error_on_one_channel_does_not_stop_the_rest(self, env):
        broken = add_ticket(env, TICKET)
        ok = add_ticket(env, TICKET_2)
        ok.messages[CONTROL] = FakeMessage(CONTROL, ["old"])

        async def boom(mid):
            raise RuntimeError("weird channel")

        broken.fetch_message = boom
        bot = SimpleNamespace(get_channel=env.guild.get_channel, add_view=lambda v, message_id=None: None)
        run(restore_ticket_views(bot))
        assert ok.messages[CONTROL].edits
