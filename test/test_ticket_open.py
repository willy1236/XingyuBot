"""starDiscord/ticket_lobby.py 的開單流程與開單用的 repository 方法（假 Discord，真實 PostgreSQL）。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import discord
import pytest
from test_identity import repo  # noqa: F401

from starDiscord import ticket_lobby
from starDiscord.ticket_lobby import TicketOpenError, open_ticket, ticket_channel_name
from starDiscord.uiElement.view import TicketChannelView, TicketLobbyView, ticket_open_refusal_text
from starlib import sclient
from starlib.database import TicketChannel, TicketChannelLobby
from starlib.utils import nowtz

GUILD_ID = 8_800_000_000_000_101
LOBBY_A, LOBBY_B = 8_800_000_000_000_111, 8_800_000_000_000_112
CATEGORY = 8_800_000_000_000_121
MESSAGE_A, MESSAGE_B = 8_800_000_000_000_131, 8_800_000_000_000_132
ROLE_MANAGER, ROLE_OTHER, ROLE_CATEGORY = 8_800_000_000_000_151, 8_800_000_000_000_152, 8_800_000_000_000_153
USER_1, USER_2, USER_3 = 8_800_000_000_000_161, 8_800_000_000_000_162, 8_800_000_000_000_163
CREATED = datetime(2026, 1, 1, tzinfo=UTC)

OPEN = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)


def http_error(status=500):
    return discord.HTTPException(SimpleNamespace(status=status, reason="boom"), "boom")


def not_found():
    return discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "unknown")


class Target:
    """可當覆寫鍵的身分組或成員。"""

    def __init__(self, tid: int, name: str = "x"):
        self.id = tid
        self.name = name
        self.mention = f"<@{tid}>"

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        return isinstance(other, Target) and other.id == self.id

    def __str__(self):
        return self.name


class FakeMessage:
    def __init__(self, mid: int):
        self.id = mid
        self.pinned = False
        self.fail_pin = False

    async def pin(self):
        if self.fail_pin:
            raise http_error(403)
        self.pinned = True


class FakeTicketChannel:
    def __init__(self, guild: FakeGuild, cid: int, name: str, kwargs: dict):
        self.guild = guild
        self.id = cid
        self.name = name
        self.kwargs = kwargs
        self.mention = f"<#{cid}>"
        self.sent: list[tuple[str, dict]] = []
        self.deleted = False
        self.message: FakeMessage | None = None

    async def send(self, content=None, **kwargs):
        if self.guild.fail_send:
            raise http_error(403)
        self.sent.append((content, kwargs))
        self.message = FakeMessage(self.id + 1)
        self.message.fail_pin = self.guild.fail_pin
        return self.message

    async def delete(self, *, reason=None):
        self.deleted = True
        self.guild.channels.pop(self.id, None)


class FakeCategory:
    type = discord.ChannelType.category

    def __init__(self, guild: FakeGuild):
        self.guild = guild
        self.id = CATEGORY
        self.overwrites = {guild.roles[ROLE_CATEGORY]: discord.PermissionOverwrite(view_channel=True)}

    async def create_text_channel(self, *, name, **kwargs):
        if self.guild.fail_create:
            raise http_error(403)
        # 讓同時按下的流程有機會交錯
        for _ in range(3):
            await asyncio.sleep(0)
        self.guild.next_id += 10
        channel = FakeTicketChannel(self.guild, self.guild.next_id, name, kwargs)
        self.guild.channels[channel.id] = channel
        self.guild.created.append(channel)
        return channel


class FakeLobbyChannel:
    type = discord.ChannelType.text

    def __init__(self, cid: int, message_id: int):
        self.id = cid
        self.message_ids = {message_id}

    async def fetch_message(self, mid: int):
        if mid not in self.message_ids:
            raise not_found()
        return SimpleNamespace(id=mid)


class FakeGuild:
    def __init__(self):
        self.id = GUILD_ID
        self.roles = {r: Target(r) for r in (ROLE_MANAGER, ROLE_OTHER, ROLE_CATEGORY)}
        self.default_role = Target(GUILD_ID, "@everyone")
        self.me = Target(1, "bot")
        self.category = FakeCategory(self)
        self.channels: dict[int, object] = {
            CATEGORY: self.category,
            LOBBY_A: FakeLobbyChannel(LOBBY_A, MESSAGE_A),
            LOBBY_B: FakeLobbyChannel(LOBBY_B, MESSAGE_B),
        }
        self.created: list[FakeTicketChannel] = []
        self.next_id = 8_800_000_000_001_000
        self.fail_create = False
        self.fail_send = False
        self.fail_pin = False

    def get_channel(self, cid):
        return self.channels.get(cid)

    def get_role(self, rid):
        return self.roles.get(rid)


@pytest.fixture
def env(repo, monkeypatch):  # noqa: F811
    monkeypatch.setattr(ticket_lobby, "sqldb", repo)
    # 鎖綁定第一次等待時的事件迴圈；每個測試用自己的迴圈
    monkeypatch.setattr(ticket_lobby, "_locks", {})
    monkeypatch.setattr(sclient, "bot", SimpleNamespace(add_view=lambda *a, **k: None))
    return SimpleNamespace(guild=FakeGuild(), repo=repo)


def add_lobby(env, channel_id=LOBBY_A, message_id=MESSAGE_A, managers=(ROLE_MANAGER,), **kw):
    env.repo.merge(
        TicketChannelLobby(
            channel_id=channel_id,
            category_id=1,
            guild_id=GUILD_ID,
            message_id=message_id,
            ticket_category_id=CATEGORY,
            **{"name_prefix": "report", **kw},
        )
    )
    env.repo.set_lobby_manager_roles(channel_id, list(managers))


def add_ticket(env, cid, creator, *, lobby=LOBBY_A, closed=False, in_discord=True):
    env.repo.merge(
        TicketChannel(
            channel_id=cid,
            guild_id=GUILD_ID,
            creator_id=creator,
            created_at=CREATED,
            closed_at=CREATED if closed else None,
            closer_id=USER_3 if closed else None,
            lobby_channel_id=lobby,
        )
    )
    if in_discord:
        env.guild.channels[cid] = SimpleNamespace(id=cid)


def user(uid):
    return Target(uid, f"user{uid}")


def open_(env, uid, lobby=LOBBY_A):
    return asyncio.run(open_ticket(env.guild, lobby, user(uid)))


def refused(env, uid, lobby=LOBBY_A) -> TicketOpenError:
    with pytest.raises(TicketOpenError) as e:
        open_(env, uid, lobby)
    return e.value


def records(env, lobby=LOBBY_A):
    return env.repo.list_lobby_ticket_channels(lobby)


# ====== 命名與流水號 ======


def test_channel_name_pads_to_four_digits_and_grows_past_9999():
    assert ticket_channel_name("report", 1) == "report-0001"
    assert ticket_channel_name("report", 9999) == "report-9999"
    assert ticket_channel_name("report", 10000) == "report-10000"


def test_open_names_by_lobby_prefix_and_writes_record(env):
    add_lobby(env)
    channel = open_(env, USER_1)

    assert channel.name == "report-0001"
    assert channel.kwargs["topic"] == f"Ticket channel for user{USER_1} ({USER_1})"
    assert channel.kwargs["reason"]
    [rec] = records(env)
    assert (rec.channel_id, rec.creator_id, rec.lobby_channel_id, rec.number) == (channel.id, USER_1, LOBBY_A, 1)
    assert rec.view_message_id == channel.message.id
    assert rec.closed_at is None
    assert channel.message.pinned
    content, kwargs = channel.sent[0]
    assert f"<@{USER_1}>" in content
    assert isinstance(kwargs["view"], TicketChannelView)
    assert env.repo.get_ticket_lobby_snapshot(LOBBY_A)["next_number"] == 2


def test_numbers_increase_per_lobby_and_are_not_reused(env):
    add_lobby(env, one_per_user=False)
    add_lobby(env, LOBBY_B, MESSAGE_B, name_prefix="appeal")
    first = open_(env, USER_1)
    # 手動刪除第一張後，號碼不回收
    env.guild.channels.pop(first.id)
    assert open_(env, USER_1).name == "report-0002"
    assert open_(env, USER_2).name == "report-0003"
    assert open_(env, USER_1, LOBBY_B).name == "appeal-0001"


def test_number_past_9999_keeps_counting(env):
    add_lobby(env, one_per_user=False, next_number=9999)
    assert open_(env, USER_1).name == "report-9999"
    assert open_(env, USER_1).name == "report-10000"
    assert [r.number for r in records(env)] == [9999, 10000]


# ====== 可見範圍 ======


def test_overwrites_copy_category_hide_everyone_and_open_for_creator_managers_bot(env):
    add_lobby(env, managers=(ROLE_MANAGER,))
    channel = open_(env, USER_1)
    ow = channel.kwargs["overwrites"]
    roles = env.guild.roles

    assert ow[env.guild.default_role] == discord.PermissionOverwrite(view_channel=False)
    assert ow[roles[ROLE_CATEGORY]] == discord.PermissionOverwrite(view_channel=True)
    assert ow[roles[ROLE_MANAGER]] == OPEN
    assert ow[user(USER_1)] == OPEN
    assert ow[env.guild.me] == OPEN
    # 其他大廳的管理身分組不在覆寫裡
    assert roles[ROLE_OTHER] not in ow
    assert set(ow) == {env.guild.default_role, roles[ROLE_CATEGORY], roles[ROLE_MANAGER], user(USER_1), env.guild.me}
    # 分類本身的覆寫沒被改到
    assert set(env.guild.category.overwrites) == {roles[ROLE_CATEGORY]}


def test_overwrites_use_each_lobby_own_managers(env):
    add_lobby(env, managers=(ROLE_MANAGER,))
    add_lobby(env, LOBBY_B, MESSAGE_B, managers=(ROLE_OTHER,))
    ow = open_(env, USER_1, LOBBY_B).kwargs["overwrites"]
    assert ow[env.guild.roles[ROLE_OTHER]] == OPEN
    assert env.guild.roles[ROLE_MANAGER] not in ow


def test_deleted_manager_role_is_skipped(env):
    add_lobby(env, managers=(ROLE_MANAGER, 8_800_000_000_000_199))
    ow = open_(env, USER_1).kwargs["overwrites"]
    assert ow[env.guild.roles[ROLE_MANAGER]] == OPEN
    assert len(ow) == 5


# ====== 每人一張 ======


def test_one_per_user_refuses_second_in_same_lobby_with_existing_channel(env):
    add_lobby(env)
    first = open_(env, USER_1)
    err = refused(env, USER_1)
    assert err.code == "already_open"
    assert err.existing_channel_id == first.id
    assert len(records(env)) == 1
    # 被拒不消耗流水號
    assert env.repo.get_ticket_lobby_snapshot(LOBBY_A)["next_number"] == 2


def test_one_per_user_counts_locked_ticket(env):
    add_lobby(env)
    add_ticket(env, 8_800_000_000_000_501, USER_1, closed=True)
    assert refused(env, USER_1).existing_channel_id == 8_800_000_000_000_501


def test_one_per_user_is_per_lobby(env):
    add_lobby(env)
    add_lobby(env, LOBBY_B, MESSAGE_B, name_prefix="appeal")
    open_(env, USER_1)
    assert open_(env, USER_1, LOBBY_B).name == "appeal-0001"


def test_one_per_user_off_allows_more(env):
    add_lobby(env, one_per_user=False)
    open_(env, USER_1)
    assert open_(env, USER_1).name == "report-0002"


def test_manually_deleted_ticket_is_cleaned_then_user_can_open(env):
    add_lobby(env)
    add_ticket(env, 8_800_000_000_000_501, USER_1, in_discord=False)
    channel = open_(env, USER_1)
    assert [r.channel_id for r in records(env)] == [channel.id]
    assert env.repo.get_ticket_channel(8_800_000_000_000_501) is None


# ====== 上限 ======


def test_max_open_counts_locked_and_frees_after_delete(env):
    add_lobby(env, max_open=2)
    add_ticket(env, 8_800_000_000_000_501, USER_1, closed=True)
    add_ticket(env, 8_800_000_000_000_502, USER_2)
    assert refused(env, USER_3).code == "full"
    # 刪除一張（Discord 上手動刪除）後可開，舊紀錄同時清掉
    env.guild.channels.pop(8_800_000_000_000_502)
    channel = open_(env, USER_3)
    assert sorted(r.channel_id for r in records(env)) == sorted([8_800_000_000_000_501, channel.id])


def test_max_open_is_per_lobby(env):
    add_lobby(env, max_open=1)
    add_lobby(env, LOBBY_B, MESSAGE_B, max_open=1)
    open_(env, USER_1)
    assert open_(env, USER_2, LOBBY_B)
    assert refused(env, USER_3).code == "full"


def test_unassigned_tickets_do_not_count(env):
    add_lobby(env, max_open=1)
    add_ticket(env, 8_800_000_000_000_501, USER_2, lobby=None)
    assert open_(env, USER_1)


def test_concurrent_presses_open_only_up_to_limit(env):
    add_lobby(env, max_open=1, one_per_user=False)

    async def both():
        return await asyncio.gather(
            open_ticket(env.guild, LOBBY_A, user(USER_1)),
            open_ticket(env.guild, LOBBY_A, user(USER_2)),
            return_exceptions=True,
        )

    results = asyncio.run(both())
    opened = [r for r in results if not isinstance(r, Exception)]
    errors = [r for r in results if isinstance(r, Exception)]
    assert len(opened) == 1
    assert [e.code for e in errors] == ["full"]
    assert len(env.guild.created) == 1
    assert len(records(env)) == 1


def test_concurrent_presses_by_same_user_open_one(env):
    add_lobby(env)

    async def twice():
        return await asyncio.gather(
            open_ticket(env.guild, LOBBY_A, user(USER_1)),
            open_ticket(env.guild, LOBBY_A, user(USER_1)),
            return_exceptions=True,
        )

    results = asyncio.run(twice())
    assert sum(not isinstance(r, Exception) for r in results) == 1
    assert len(env.guild.created) == 1


# ====== 已移除、失效的大廳 ======


def test_removed_lobby_cannot_open(env):
    add_lobby(env)
    assert env.repo.remove_ticket_lobby(LOBBY_A)
    assert refused(env, USER_1).code == "lobby_removed"
    assert env.guild.created == []


def test_unknown_lobby_or_other_guild_cannot_open(env):
    assert refused(env, USER_1).code == "lobby_removed"
    env.repo.merge(
        TicketChannelLobby(channel_id=LOBBY_A, category_id=1, guild_id=GUILD_ID + 1, message_id=MESSAGE_A, ticket_category_id=CATEGORY)
    )
    assert refused(env, USER_1).code == "lobby_removed"


def test_lobby_with_deleted_category_cannot_open(env):
    add_lobby(env)
    env.guild.channels.pop(CATEGORY)
    assert refused(env, USER_1).code == "lobby_invalid"
    assert env.repo.get_ticket_lobby_snapshot(LOBBY_A)["next_number"] == 1


def test_lobby_with_deleted_message_cannot_open(env):
    add_lobby(env)
    env.guild.channels[LOBBY_A].message_ids.clear()
    assert refused(env, USER_1).code == "lobby_invalid"


def test_lobby_without_ticket_category_cannot_open(env):
    add_lobby(env)
    env.repo.update_ticket_lobby_if(LOBBY_A, {}, {"ticket_category_id": None})
    assert refused(env, USER_1).code == "lobby_invalid"


# ====== Discord 失敗 ======


def test_create_failure_reports_discord_error_and_writes_nothing(env):
    add_lobby(env)
    env.guild.fail_create = True
    err = refused(env, USER_1)
    assert err.code == "discord_error"
    assert err.message == "boom"
    assert records(env) == []


def test_send_failure_deletes_channel_and_writes_nothing(env):
    add_lobby(env)
    env.guild.fail_send = True
    assert refused(env, USER_1).code == "discord_error"
    [channel] = env.guild.created
    assert channel.deleted
    assert records(env) == []


def test_db_failure_deletes_channel(env, monkeypatch):
    add_lobby(env)

    def boom(_):
        raise RuntimeError("db down")

    monkeypatch.setattr(env.repo, "merge", boom)
    assert refused(env, USER_1).code == "save_failed"
    assert env.guild.created[0].deleted


def test_pin_failure_still_opens(env):
    add_lobby(env)
    env.guild.fail_pin = True
    channel = open_(env, USER_1)
    assert not channel.message.pinned
    assert len(records(env)) == 1


# ====== 按鈕 ======


class FakeInteraction:
    def __init__(self, guild, channel_id, member):
        self.guild = guild
        self.channel_id = channel_id
        self.user = member
        self.deferred = None
        self.followups: list[tuple[str, dict]] = []
        self.response = SimpleNamespace(defer=self._defer)
        self.followup = SimpleNamespace(send=self._send)

    async def _defer(self, **kwargs):
        self.deferred = kwargs

    async def _send(self, content, **kwargs):
        self.followups.append((content, kwargs))


def press(env, uid, lobby=LOBBY_A) -> FakeInteraction:
    interaction = FakeInteraction(env.guild, lobby, user(uid))

    async def go():
        button = TicketLobbyView(lobby).children[0]
        await button.callback(interaction)

    asyncio.run(go())
    return interaction


def test_button_opens_and_replies_only_to_presser(env):
    add_lobby(env)
    interaction = press(env, USER_1)
    assert interaction.deferred == {"ephemeral": True}
    [(content, kwargs)] = interaction.followups
    assert env.guild.created[0].mention in content
    assert kwargs == {"ephemeral": True}


def test_button_refusal_tells_presser_existing_channel(env):
    add_lobby(env)
    first = open_(env, USER_1)
    [(content, kwargs)] = press(env, USER_1).followups
    assert f"<#{first.id}>" in content
    assert kwargs == {"ephemeral": True}


def test_button_full_message(env):
    add_lobby(env, max_open=1, one_per_user=False)
    open_(env, USER_1)
    [(content, _)] = press(env, USER_2).followups
    assert "額滿" in content


@pytest.mark.parametrize("code", ["already_open", "full", "lobby_removed", "lobby_invalid", "discord_error", "save_failed"])
def test_every_refusal_has_text(code):
    assert ticket_open_refusal_text(TicketOpenError(code, existing_channel_id=1, message="m"))


# ====== repository ======


def test_take_ticket_number_returns_current_and_increments(env):
    add_lobby(env, next_number=5)
    assert env.repo.take_ticket_number(LOBBY_A) == 5
    assert env.repo.take_ticket_number(LOBBY_A) == 6
    assert env.repo.get_ticket_lobby_snapshot(LOBBY_A)["next_number"] == 7


def test_take_ticket_number_none_for_removed_or_missing(env):
    assert env.repo.take_ticket_number(LOBBY_A) is None
    add_lobby(env)
    env.repo.remove_ticket_lobby(LOBBY_A)
    assert env.repo.take_ticket_number(LOBBY_A) is None


def test_count_and_find_include_locked_and_scope_to_lobby(env):
    add_lobby(env)
    add_lobby(env, LOBBY_B, MESSAGE_B)
    add_ticket(env, 8_800_000_000_000_501, USER_1, closed=True)
    add_ticket(env, 8_800_000_000_000_502, USER_2)
    add_ticket(env, 8_800_000_000_000_503, USER_1, lobby=LOBBY_B)
    assert env.repo.count_open_lobby_tickets(LOBBY_A) == 2
    assert env.repo.count_open_lobby_tickets(LOBBY_B) == 1
    assert env.repo.find_user_ticket(LOBBY_A, USER_1) == 8_800_000_000_000_501
    assert env.repo.find_user_ticket(LOBBY_B, USER_1) == 8_800_000_000_000_503
    assert env.repo.find_user_ticket(LOBBY_B, USER_2) is None


def test_record_created_at_is_now(env):
    add_lobby(env)
    before = nowtz()
    open_(env, USER_1)
    [rec] = records(env)
    assert rec.created_at >= before.replace(microsecond=0)
