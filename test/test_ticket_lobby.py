"""starDiscord/ticket_lobby.py：大廳的建立、更新、移除（假 Discord，真實 PostgreSQL）。"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import discord
import pytest
from test_identity import repo  # noqa: F401

from starDiscord import ticket_lobby
from starDiscord.ticket_lobby import LobbyConflict, LobbyError, LobbyValues, NewChannel, remove_lobby, save_lobby
from starDiscord.uiElement.view import TicketLobbyView
from starlib import sclient
from starlib.database import TicketChannel, TicketChannelLobby
from starlib.message_content import EmbedContent, MessageContent, from_json

GUILD_ID = 8_800_000_000_000_001
LOBBY_A = 8_800_000_000_000_011
LOBBY_NEW = 8_800_000_000_000_012
CATEGORY_TICKET = 8_800_000_000_000_021
CATEGORY_OWN = 8_800_000_000_000_022
OLD_MESSAGE = 8_800_000_000_000_031
T1, T2 = 8_800_000_000_000_041, 8_800_000_000_000_042
ROLE_1, ROLE_2 = 8_800_000_000_000_051, 8_800_000_000_000_052
CREATED = datetime(2026, 1, 1, tzinfo=UTC)


def http_error(status=500):
    return discord.HTTPException(SimpleNamespace(status=status, reason="boom"), "boom")


def not_found():
    return discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "unknown")


class FakeMessage:
    def __init__(self, mid: int, content: str | None = "舊"):
        self.id = mid
        self.content = content
        self.embeds: list = []
        self.edits: list[dict] = []
        self.deleted = False
        self.fail_edit = False

    @property
    def jump_url(self) -> str:
        return f"https://discord.com/channels/{GUILD_ID}/x/{self.id}"

    async def edit(self, **kwargs):
        if self.fail_edit:
            raise http_error()
        self.edits.append(kwargs)

    async def delete(self):
        self.deleted = True


class FakeChannel:
    def __init__(self, cid: int, kind=discord.ChannelType.text, category_id: int | None = CATEGORY_OWN):
        self.id = cid
        self.type = kind
        self.category_id = category_id
        self.messages: dict[int, FakeMessage] = {}
        self.sent: list[tuple[FakeMessage, dict]] = []
        self.fail_send = False
        self.deleted = False
        self.permission_calls: list[tuple[int, object, str | None]] = []
        self.next_id = 8_800_000_000_000_900

    async def fetch_message(self, mid: int):
        if mid not in self.messages:
            raise not_found()
        return self.messages[mid]

    async def send(self, **kwargs):
        if self.fail_send:
            raise http_error(403)
        self.next_id += 1
        m = FakeMessage(self.next_id, kwargs.get("content"))
        self.messages[m.id] = m
        self.sent.append((m, kwargs))
        return m

    async def set_permissions(self, role, *, overwrite, reason=None):
        self.permission_calls.append((role.id, overwrite, reason))

    async def delete(self):
        self.deleted = True


class FakeGuild:
    def __init__(self):
        self.id = GUILD_ID
        self.me = SimpleNamespace(id=1, display_avatar=SimpleNamespace(url="https://cdn/bot.png"))
        self.lobby = FakeChannel(LOBBY_A)
        self.ticket_category = FakeChannel(CATEGORY_TICKET, kind=discord.ChannelType.category, category_id=None)
        self.channels = {c.id: c for c in (self.lobby, self.ticket_category)}
        self.roles = {r: SimpleNamespace(id=r) for r in (ROLE_1, ROLE_2)}
        self.created: list[tuple[str, dict]] = []

    def get_channel(self, cid):
        return self.channels.get(cid)

    def get_role(self, rid):
        return self.roles.get(rid)

    async def create_text_channel(self, name, **kwargs):
        if getattr(self, "fail_create", False):
            raise http_error(403)
        c = FakeChannel(LOBBY_NEW)
        self.channels[c.id] = c
        self.created.append((name, kwargs))
        return c


class FakeBot:
    def __init__(self):
        self.views: list[tuple[int | None, discord.ui.View]] = []

    def add_view(self, view, message_id=None):
        self.views.append((message_id, view))


@pytest.fixture
def env(repo, monkeypatch):  # noqa: F811
    monkeypatch.setattr(ticket_lobby, "sqldb", repo)
    bot = FakeBot()
    monkeypatch.setattr(sclient, "bot", bot)
    return SimpleNamespace(guild=FakeGuild(), bot=bot, repo=repo)


def values(**kw) -> LobbyValues:
    base = dict(
        channel=LOBBY_A,
        ticket_category_id=CATEGORY_TICKET,
        manager_role_ids=[ROLE_1],
        name_prefix="report",
        one_per_user=True,
        max_open=None,
        message=MessageContent(embed=EmbedContent(description="請按按鈕")),
        button_label="開單",
        button_emoji=None,
        reason="測試 透過後台：大廳",
    )
    base.update(kw)
    return LobbyValues(**base)


def run(coro):
    return asyncio.run(coro)


def add_old_lobby(env, **kw):
    """已存在的大廳與它的訊息"""
    msg = FakeMessage(OLD_MESSAGE)
    env.guild.lobby.messages[OLD_MESSAGE] = msg
    env.repo.merge(
        TicketChannelLobby(
            channel_id=LOBBY_A,
            category_id=1,
            guild_id=GUILD_ID,
            message_id=OLD_MESSAGE,
            ticket_category_id=CATEGORY_TICKET,
            name_prefix="old",
            **kw,
        )
    )
    env.repo.set_lobby_manager_roles(LOBBY_A, [ROLE_1])
    return msg


def add_ticket(env, cid, *, closed=False, saved=None):
    env.repo.merge(
        TicketChannel(
            channel_id=cid,
            guild_id=env.guild.id,
            creator_id=7,
            created_at=CREATED,
            closed_at=CREATED if closed else None,
            closer_id=8 if closed else None,
            lobby_channel_id=LOBBY_A,
            locked_overwrites_json=None if saved is None else json.dumps(saved),
        )
    )
    env.guild.channels[cid] = FakeChannel(cid)


class TestCreate:
    def test_existing_channel_sends_message_with_view_and_saves(self, env):
        result = run(save_lobby(env.guild, values(button_emoji="🎫", manager_role_ids=[ROLE_2, ROLE_1])))

        [(message, kwargs)] = env.guild.lobby.sent
        assert kwargs["embeds"][0].description == "請按按鈕"
        assert kwargs["allowed_mentions"].everyone is False
        button = kwargs["view"].children[0]
        assert (button.label, str(button.emoji), button.custom_id) == ("開單", "🎫", f"create_ticket_{LOBBY_A}")
        assert env.bot.views[0][0] == message.id
        assert (result.channel_id, result.message_id, result.failures) == (LOBBY_A, message.id, [])

        snap = env.repo.get_ticket_lobby_snapshot(LOBBY_A)
        assert snap["message_id"] == message.id
        assert snap["manager_role_ids"] == sorted([ROLE_1, ROLE_2])
        assert (snap["name_prefix"], snap["button_label"], snap["button_emoji"], snap["category_id"]) == (
            "report",
            "開單",
            "🎫",
            CATEGORY_OWN,
        )
        assert from_json(snap["content_json"]).embed.description == "請按按鈕"  # pyright: ignore[reportOptionalMemberAccess]

    def test_new_channel_is_created_in_category(self, env):
        result = run(save_lobby(env.guild, values(channel=NewChannel("開單", CATEGORY_TICKET))))
        assert env.guild.created == [("開單", {"category": env.guild.ticket_category, "reason": "測試 透過後台：大廳"})]
        assert result.channel_id == LOBBY_NEW
        assert env.repo.get_ticket_lobby_snapshot(LOBBY_NEW) is not None

    def test_message_none_uses_default_content(self, env):
        run(save_lobby(env.guild, values(message=None, button_label=None)))
        [(_, kwargs)] = env.guild.lobby.sent
        assert kwargs["embeds"][0].description == "點擊下方按鈕以建立私人頻道"
        assert kwargs["view"].children[0].label == "建立私人頻道"

    def test_active_lobby_on_channel_is_rejected_without_side_effects(self, env):
        add_old_lobby(env)
        with pytest.raises(LobbyError) as e:
            run(save_lobby(env.guild, values()))
        assert e.value.code == "lobby_exists"
        assert env.guild.lobby.sent == []
        assert env.repo.get_ticket_lobby_snapshot(LOBBY_A)["name_prefix"] == "old"

    def test_removed_lobby_is_overwritten_keeping_next_number(self, env):
        add_old_lobby(env, next_number=9)
        env.repo.mark_lobby_removed(LOBBY_A)
        run(save_lobby(env.guild, values()))
        snap = env.repo.get_ticket_lobby_snapshot(LOBBY_A)
        assert (snap["name_prefix"], snap["next_number"], snap["removed_at"]) == ("report", 9, None)

    def test_missing_or_non_text_channel(self, env):
        with pytest.raises(LobbyError) as e:
            run(save_lobby(env.guild, values(channel=12345)))
        assert e.value.code == "channel_not_found"
        with pytest.raises(LobbyError) as e:
            run(save_lobby(env.guild, values(channel=CATEGORY_TICKET)))
        assert e.value.code == "channel_not_found"

    def test_new_channel_with_bad_category(self, env):
        with pytest.raises(LobbyError) as e:
            run(save_lobby(env.guild, values(channel=NewChannel("x", LOBBY_A))))
        assert e.value.code == "category_not_found"
        assert env.guild.created == []

    def test_send_failure_deletes_created_channel(self, env):
        original = env.guild.create_text_channel

        async def create_failing_send(name, **kwargs):
            c = await original(name, **kwargs)
            c.fail_send = True
            return c

        env.guild.create_text_channel = create_failing_send  # pyright: ignore[reportAttributeAccessIssue]
        with pytest.raises(LobbyError) as e:
            run(save_lobby(env.guild, values(channel=NewChannel("x", CATEGORY_TICKET))))
        assert e.value.code == "discord_error"
        assert env.guild.channels[LOBBY_NEW].deleted
        assert env.repo.get_ticket_lobby_snapshot(LOBBY_NEW) is None

    def test_create_channel_failure(self, env):
        env.guild.fail_create = True  # pyright: ignore[reportAttributeAccessIssue]
        with pytest.raises(LobbyError) as e:
            run(save_lobby(env.guild, values(channel=NewChannel("x", CATEGORY_TICKET))))
        assert e.value.code == "discord_error"

    def test_db_failure_deletes_message_and_created_channel(self, env, monkeypatch):
        def boom(*args, **kwargs):
            raise RuntimeError("db down")

        monkeypatch.setattr(env.repo, "insert_ticket_lobby", boom)
        with pytest.raises(LobbyError) as e:
            run(save_lobby(env.guild, values(channel=NewChannel("x", CATEGORY_TICKET))))
        assert e.value.code == "save_failed"
        created = env.guild.channels[LOBBY_NEW]
        assert created.sent[0][0].deleted
        assert created.deleted


class TestUpdate:
    def original(self, **kw):
        return {
            "ticket_category_id": CATEGORY_TICKET,
            "name_prefix": "old",
            "one_per_user": True,
            "max_open": None,
            "content_json": None,
            "button_label": None,
            "button_emoji": None,
            **kw,
        }

    def test_edits_message_in_place(self, env):
        old = add_old_lobby(env)
        result = run(
            save_lobby(
                env.guild, values(previous_channel_id=LOBBY_A, original=self.original(), manager_role_ids=[ROLE_1])
            )
        )
        assert env.guild.lobby.sent == []
        [edit] = old.edits
        assert edit["embeds"][0].description == "請按按鈕"
        assert edit["view"].children[0].label == "開單"
        assert result.message_id == OLD_MESSAGE
        snap = env.repo.get_ticket_lobby_snapshot(LOBBY_A)
        assert (snap["name_prefix"], snap["message_id"]) == ("report", OLD_MESSAGE)

    def test_message_none_keeps_stored_content(self, env):
        stored = MessageContent(content="存下的")
        old = add_old_lobby(env, content_json=stored.model_dump_json())
        run(
            save_lobby(
                env.guild,
                values(
                    previous_channel_id=LOBBY_A,
                    message=None,
                    original=self.original(content_json=stored.model_dump_json()),
                ),
            )
        )
        assert old.edits[0]["content"] == "存下的"

    def test_conflict_restores_message_and_writes_nothing(self, env):
        old = add_old_lobby(env, max_open=5)
        with pytest.raises(LobbyConflict) as e:
            run(save_lobby(env.guild, values(previous_channel_id=LOBBY_A, original=self.original())))
        assert not e.value.deleted
        assert len(old.edits) == 2  # 先編輯，衝突後還原
        assert old.edits[1]["content"] == "舊"
        assert env.repo.get_ticket_lobby_snapshot(LOBBY_A)["name_prefix"] == "old"

    def test_removed_lobby_is_deleted_conflict(self, env):
        add_old_lobby(env)
        env.repo.mark_lobby_removed(LOBBY_A)
        with pytest.raises(LobbyConflict) as e:
            run(save_lobby(env.guild, values(previous_channel_id=LOBBY_A, original=self.original())))
        assert e.value.deleted

    def test_deleted_message_is_resent(self, env):
        add_old_lobby(env)
        del env.guild.lobby.messages[OLD_MESSAGE]
        result = run(save_lobby(env.guild, values(previous_channel_id=LOBBY_A, original=self.original())))
        assert len(env.guild.lobby.sent) == 1
        assert result.message_id == env.guild.lobby.sent[0][0].id
        assert env.repo.get_ticket_lobby_snapshot(LOBBY_A)["message_id"] == result.message_id

    def test_fetch_error_other_than_not_found_is_not_resent(self, env):
        add_old_lobby(env)

        async def forbidden(mid):
            raise discord.Forbidden(SimpleNamespace(status=403, reason="no"), "missing")

        env.guild.lobby.fetch_message = forbidden  # pyright: ignore[reportAttributeAccessIssue]
        with pytest.raises(LobbyError) as e:
            run(save_lobby(env.guild, values(previous_channel_id=LOBBY_A, original=self.original())))
        assert e.value.code == "discord_error"
        assert env.guild.lobby.sent == []

    def test_edit_failure_changes_nothing(self, env):
        old = add_old_lobby(env)
        old.fail_edit = True
        with pytest.raises(LobbyError) as e:
            run(save_lobby(env.guild, values(previous_channel_id=LOBBY_A, original=self.original())))
        assert e.value.code == "discord_error"
        assert env.repo.get_ticket_lobby_snapshot(LOBBY_A)["name_prefix"] == "old"

    def test_channel_change_moves_tickets_and_keeps_number(self, env):
        add_old_lobby(env, next_number=6)
        add_ticket(env, T1)
        del env.guild.channels[LOBBY_A]  # 原大廳頻道被刪除
        new = FakeChannel(LOBBY_NEW)
        env.guild.channels[LOBBY_NEW] = new
        result = run(
            save_lobby(env.guild, values(channel=LOBBY_NEW, previous_channel_id=LOBBY_A, original=self.original()))
        )
        assert result.channel_id == LOBBY_NEW
        assert len(new.sent) == 1
        assert env.repo.get_ticket_lobby_snapshot(LOBBY_A) is None
        snap = env.repo.get_ticket_lobby_snapshot(LOBBY_NEW)
        assert (snap["next_number"], snap["message_id"]) == (6, new.sent[0][0].id)
        assert env.repo.get_ticket_channel(T1).lobby_channel_id == LOBBY_NEW

    def test_channel_change_refused_while_old_channel_exists(self, env):
        add_old_lobby(env)
        env.guild.channels[LOBBY_NEW] = FakeChannel(LOBBY_NEW)
        with pytest.raises(LobbyError) as e:
            run(save_lobby(env.guild, values(channel=LOBBY_NEW, previous_channel_id=LOBBY_A, original=self.original())))
        assert e.value.code == "channel_in_use"
        with pytest.raises(LobbyError) as e:
            run(
                save_lobby(
                    env.guild,
                    values(
                        channel=NewChannel("x", CATEGORY_TICKET), previous_channel_id=LOBBY_A, original=self.original()
                    ),
                )
            )
        assert e.value.code == "channel_in_use"
        assert env.guild.created == []

    def test_channel_change_to_active_lobby_is_rejected(self, env):
        add_old_lobby(env)
        env.repo.merge(
            TicketChannelLobby(
                channel_id=LOBBY_NEW, category_id=1, guild_id=GUILD_ID, message_id=1, ticket_category_id=1
            )
        )
        env.guild.channels[LOBBY_NEW] = FakeChannel(LOBBY_NEW)
        del env.guild.channels[LOBBY_A]
        with pytest.raises(LobbyError) as e:
            run(save_lobby(env.guild, values(channel=LOBBY_NEW, previous_channel_id=LOBBY_A, original=self.original())))
        assert e.value.code == "lobby_exists"

    def test_manager_role_changes_applied_to_tickets(self, env):
        add_old_lobby(env)
        add_ticket(env, T1)
        add_ticket(env, T2, closed=True, saved={f"role:{ROLE_1}": True})
        result = run(
            save_lobby(
                env.guild,
                values(previous_channel_id=LOBBY_A, original=self.original(), manager_role_ids=[ROLE_2]),
            )
        )
        assert result.failures == []
        open_calls = env.guild.channels[T1].permission_calls
        assert [(c[0], c[2]) for c in open_calls] == [(ROLE_2, "測試 透過後台：大廳"), (ROLE_1, "測試 透過後台：大廳")]
        assert open_calls[1][1] is None
        saved = json.loads(env.repo.get_ticket_channel(T2).locked_overwrites_json)
        assert saved == {f"role:{ROLE_2}": True}
        assert env.repo.get_ticket_lobby_snapshot(LOBBY_A)["manager_role_ids"] == [ROLE_2]

    def test_partial_failure_still_saves_and_lists_channels(self, env):
        add_old_lobby(env)
        add_ticket(env, T1)

        async def forbidden(role, *, overwrite, reason=None):
            raise discord.Forbidden(SimpleNamespace(status=403, reason="no"), "missing")

        env.guild.channels[T1].set_permissions = forbidden  # pyright: ignore[reportAttributeAccessIssue]
        result = run(
            save_lobby(
                env.guild,
                values(previous_channel_id=LOBBY_A, original=self.original(), manager_role_ids=[ROLE_1, ROLE_2]),
            )
        )
        assert [f.channel_id for f in result.failures] == [T1]
        assert env.repo.get_ticket_lobby_snapshot(LOBBY_A)["manager_role_ids"] == sorted([ROLE_1, ROLE_2])

    def test_unchanged_roles_do_not_touch_tickets(self, env):
        add_old_lobby(env)
        add_ticket(env, T1)
        run(save_lobby(env.guild, values(previous_channel_id=LOBBY_A, original=self.original())))
        assert env.guild.channels[T1].permission_calls == []


class TestRemove:
    def test_removes_button_marks_removed_and_unassigns(self, env):
        old = add_old_lobby(env)
        add_ticket(env, T1)
        run(remove_lobby(env.guild, LOBBY_A, OLD_MESSAGE))
        assert old.edits == [{"view": None}]
        assert env.repo.get_ticket_lobby_snapshot(LOBBY_A)["removed_at"] is not None
        assert env.repo.get_ticket_channel(T1).lobby_channel_id is None
        assert env.repo.list_guild_ticket_lobbies(GUILD_ID) == []

    def test_missing_message_or_channel_is_ok(self, env):
        add_old_lobby(env)
        del env.guild.lobby.messages[OLD_MESSAGE]
        run(remove_lobby(env.guild, LOBBY_A, OLD_MESSAGE))
        assert env.repo.get_ticket_lobby_snapshot(LOBBY_A)["removed_at"] is not None

    def test_missing_channel_is_ok(self, env):
        add_old_lobby(env)
        del env.guild.channels[LOBBY_A]
        run(remove_lobby(env.guild, LOBBY_A, OLD_MESSAGE))
        assert env.repo.get_ticket_lobby_snapshot(LOBBY_A)["removed_at"] is not None

    def test_edit_failure_keeps_lobby(self, env):
        old = add_old_lobby(env)
        old.fail_edit = True
        with pytest.raises(LobbyError) as e:
            run(remove_lobby(env.guild, LOBBY_A, OLD_MESSAGE))
        assert e.value.code == "discord_error"
        assert env.repo.get_ticket_lobby_snapshot(LOBBY_A)["removed_at"] is None


class TestView:
    def test_default_label_and_custom_emoji(self):
        async def build():
            default = TicketLobbyView(5).children[0]
            custom = TicketLobbyView(5, "開單", "<:ok:700000000000001>").children[0]
            return default, custom

        default, custom = run(build())
        assert (default.label, default.emoji, default.custom_id) == ("建立私人頻道", None, "create_ticket_5")
        assert custom.label == "開單"
        assert custom.emoji.id == 700000000000001
