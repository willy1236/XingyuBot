"""P-05 `/ticket setup`：新增或修改大廳、只改有填的選項、衝突參數與欄位驗證（假 Discord，真實 PostgreSQL）。"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands
from test_identity import repo  # noqa: F401  (fixture)

from starDiscord import ticket_lobby
from starDiscord.cmds import moderation as cmd
from starlib import sclient
from starlib.database import TicketChannel, TicketChannelLobby
from starlib.message_content import EmbedContent, MessageContent, from_json, to_json

GUILD_ID = 8_800_000_000_005_001
LOBBY = 8_800_000_000_005_011
OTHER_TEXT = 8_800_000_000_005_013
NEW_LOBBY = 8_800_000_000_005_012
CATEGORY_TICKET = 8_800_000_000_005_021
CATEGORY_OWN = 8_800_000_000_005_022
CATEGORY_OTHER = 8_800_000_000_005_023
OLD_MESSAGE = 8_800_000_000_005_031
T1 = 8_800_000_000_005_041
ROLE_1, ROLE_2, ROLE_3, ROLE_4, ROLE_5 = (8_800_000_000_005_051 + i for i in range(5))
ROLE_MANAGED = 8_800_000_000_005_061
FOREIGN_EMOJI = "<:far:8800000000005071>"
OWN_EMOJI_ID = 8_800_000_000_005_072
OWN_EMOJI = f"<:own:{OWN_EMOJI_ID}>"
CREATED = datetime(2026, 1, 1, tzinfo=UTC)


def forbidden():
    return discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "Missing Access")


class FakeMessage:
    def __init__(self, mid: int, content: str | None = None):
        self.id = mid
        self.content = content
        self.embeds: list = []
        self.edits: list[dict] = []

    @property
    def jump_url(self) -> str:
        return f"https://discord.com/channels/{GUILD_ID}/x/{self.id}"

    async def edit(self, **kwargs):
        self.edits.append(kwargs)

    async def delete(self, *, reason=None):
        pass


class FakeChannel:
    def __init__(self, cid: int, kind=discord.ChannelType.text, category_id: int | None = CATEGORY_OWN):
        self.id = cid
        self.type = kind
        self.category_id = category_id
        self.messages: dict[int, FakeMessage] = {}
        self.sent: list[dict] = []
        self.permission_calls: list[tuple[int, object]] = []
        self.fail_fetch: Exception | None = None
        self.fail_permissions = False
        self.perms = discord.Permissions.all()
        self.next_id = 8_800_000_000_005_900

    async def fetch_message(self, mid: int):
        if self.fail_fetch is not None:
            raise self.fail_fetch
        if mid not in self.messages:
            raise discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "unknown")
        return self.messages[mid]

    async def send(self, **kwargs):
        self.next_id += 1
        m = FakeMessage(self.next_id, kwargs.get("content"))
        self.messages[m.id] = m
        self.sent.append(kwargs)
        return m

    async def set_permissions(self, role, *, overwrite, reason=None):
        if self.fail_permissions:
            raise forbidden()
        self.permission_calls.append((role.id, overwrite))

    async def delete(self, *, reason=None):
        pass

    def permissions_for(self, _member):
        return self.perms


def role(rid: int, name: str = "role", *, default=False, managed=False):
    return SimpleNamespace(id=rid, name=name, managed=managed, is_default=lambda: default, mention=f"<@&{rid}>")


class FakeGuild:
    def __init__(self):
        self.id = GUILD_ID
        self.icon = None
        self.me = SimpleNamespace(id=1, display_avatar=SimpleNamespace(url="https://cdn/bot.png"))
        self.lobby = FakeChannel(LOBBY)
        self.other = FakeChannel(OTHER_TEXT)
        self.ticket_category = FakeChannel(CATEGORY_TICKET, kind=discord.ChannelType.category, category_id=None)
        self.own_category = FakeChannel(CATEGORY_OWN, kind=discord.ChannelType.category, category_id=None)
        self.other_category = FakeChannel(CATEGORY_OTHER, kind=discord.ChannelType.category, category_id=None)
        self.channels = {
            c.id: c for c in (self.lobby, self.other, self.ticket_category, self.own_category, self.other_category)
        }
        self.roles = {r: role(r, f"r{r % 100}") for r in (ROLE_1, ROLE_2, ROLE_3, ROLE_4, ROLE_5)}
        self.roles[GUILD_ID] = role(GUILD_ID, "@everyone", default=True)
        self.roles[ROLE_MANAGED] = role(ROLE_MANAGED, "bot role", managed=True)
        self.created: list[tuple[str, dict]] = []

    def get_channel(self, cid):
        return self.channels.get(cid)

    def get_role(self, rid):
        return self.roles.get(rid)

    def get_emoji(self, eid):
        return object() if eid == OWN_EMOJI_ID else None

    async def create_text_channel(self, name, **kwargs):
        c = FakeChannel(NEW_LOBBY, category_id=kwargs["category"].id)
        self.channels[c.id] = c
        self.created.append((name, kwargs))
        return c


class FakeBot:
    def add_view(self, view, message_id=None):
        pass


@pytest.fixture
def env(repo, monkeypatch):  # noqa: F811
    monkeypatch.setattr(ticket_lobby, "sqldb", repo)
    monkeypatch.setattr(ticket_lobby, "_locks", {})
    monkeypatch.setattr(cmd.sclient, "sqldb", repo, raising=False)
    monkeypatch.setattr(sclient, "bot", FakeBot())
    guild = FakeGuild()
    ctx = MagicMock()
    ctx.guild = guild
    ctx.author = SimpleNamespace(id=7, name="管理員")
    ctx.defer = AsyncMock()
    ctx.respond = AsyncMock()
    return SimpleNamespace(repo=repo, guild=guild, ctx=ctx, cog=cmd.moderation(MagicMock()))


OPTIONS = (
    "channel",
    "new_channel_name",
    "new_channel_category",
    "ticket_category",
    "role1",
    "role2",
    "role3",
    "clear_roles",
    "prefix",
    "one_per_user",
    "max_open",
    "clear_max_open",
    "message_text",
    "button_label",
    "button_emoji",
)


def call(env, **kw):
    """以 Discord 送進來的值呼叫指令；沒填的選項是 None，兩個「清空」預設 False。"""
    unknown = set(kw) - set(OPTIONS)
    assert not unknown, unknown
    args = {name: None for name in OPTIONS} | {"clear_roles": False, "clear_max_open": False} | kw
    for key in ("role1", "role2", "role3"):
        if isinstance(args[key], int):
            args[key] = env.guild.roles[args[key]]
    asyncio.run(env.cog.ticket_setup.callback(env.cog, env.ctx, *(args[name] for name in OPTIONS)))
    return env.ctx.respond


def reply_text(respond) -> str:
    return respond.call_args.args[0]


def reply_fields(respond) -> dict[str, str]:
    return {f.name: f.value for f in respond.call_args.kwargs["embed"].fields}


def add_lobby(env, roles=(ROLE_1,), **kw):
    """還在使用中的大廳（後台設定過）與它的訊息"""
    env.guild.lobby.messages[OLD_MESSAGE] = FakeMessage(OLD_MESSAGE)
    fields = dict(
        channel_id=LOBBY,
        category_id=CATEGORY_OWN,
        guild_id=GUILD_ID,
        message_id=OLD_MESSAGE,
        ticket_category_id=CATEGORY_TICKET,
        name_prefix="report",
        one_per_user=False,
        max_open=5,
        content_json=to_json(MessageContent(embed=EmbedContent(description="後台寫的說明"))),
        button_label="回報",
        button_emoji="📮",
    )
    env.repo.merge(TicketChannelLobby(**(fields | kw)))
    env.repo.set_lobby_manager_roles(LOBBY, list(roles))


def snap(env, cid=LOBBY) -> dict:
    return env.repo.get_ticket_lobby_snapshot(cid)


def assert_error(respond, *needles):
    text = reply_text(respond)
    assert text.startswith("錯誤")
    for needle in needles:
        assert needle in text
    assert respond.call_args.kwargs["ephemeral"] is True


class TestCreate:
    def test_existing_channel_with_roles_prefix_and_limit(self, env):
        respond = call(env, channel=env.guild.lobby, role1=ROLE_2, role2=ROLE_1, prefix="Bug Report", max_open=3)

        env.ctx.defer.assert_awaited_once_with(ephemeral=True)
        [kwargs] = env.guild.lobby.sent
        assert kwargs["embeds"][0].description == "點擊下方按鈕以建立私人頻道"
        assert kwargs["view"].children[0].custom_id == f"create_ticket_{LOBBY}"
        s = snap(env)
        assert s["manager_role_ids"] == sorted([ROLE_1, ROLE_2])
        assert (s["name_prefix"], s["max_open"], s["one_per_user"]) == ("bug-report", 3, True)
        # 私人頻道分類沒填時用大廳頻道所在的分類
        assert s["ticket_category_id"] == CATEGORY_OWN
        assert (s["button_label"], s["button_emoji"], s["removed_at"]) == (None, None, None)

        assert respond.call_args.kwargs["ephemeral"] is True
        fields = reply_fields(respond)
        assert respond.call_args.kwargs["embed"].author.name == "已新增私人頻道大廳"
        assert (fields["前綴"], fields["上限"], fields["每人一張"]) == ("bug-report", "3", "是")
        assert fields["開單按鈕"] == "建立私人頻道"
        assert "注意" not in fields

    def test_new_channel_with_name_and_category(self, env):
        call(env, new_channel_name=" 開單 ", new_channel_category=env.guild.other_category, ticket_category=env.guild.ticket_category)
        [(name, kwargs)] = env.guild.created
        assert name == "開單" and kwargs["category"] is env.guild.other_category
        assert "/ticket setup 新增私人頻道大廳" in kwargs["reason"]
        assert "透過後台" not in kwargs["reason"]
        s = snap(env, NEW_LOBBY)
        assert (s["ticket_category_id"], s["category_id"]) == (CATEGORY_TICKET, CATEGORY_OTHER)

    def test_new_channel_defaults_to_ticket_category(self, env):
        call(env, new_channel_name="開單", ticket_category=env.guild.ticket_category)
        assert env.guild.created[0][1]["category"] is env.guild.ticket_category
        assert snap(env, NEW_LOBBY)["ticket_category_id"] == CATEGORY_TICKET

    def test_new_channel_without_any_category_is_rejected(self, env):
        respond = call(env, new_channel_name="開單")
        assert_error(respond, "私人頻道分類")
        assert env.guild.created == []

    def test_channel_without_category_needs_ticket_category(self, env):
        env.guild.other.category_id = None
        respond = call(env, channel=env.guild.other)
        assert_error(respond, "私人頻道分類")
        assert snap(env, OTHER_TEXT) is None

    def test_message_text_button_and_emoji(self, env):
        call(env, channel=env.guild.lobby, message_text="有事請按", button_label="開單", button_emoji=OWN_EMOJI)
        [kwargs] = env.guild.lobby.sent
        assert kwargs["content"] == "有事請按"
        assert kwargs["embeds"][0].description == "點擊下方按鈕以建立私人頻道"  # embed 沿用預設
        button = kwargs["view"].children[0]
        assert (button.label, str(button.emoji)) == ("開單", OWN_EMOJI)
        s = snap(env)
        assert (s["button_label"], s["button_emoji"]) == ("開單", OWN_EMOJI)
        assert from_json(s["content_json"]).content == "有事請按"

    def test_removed_lobby_channel_is_set_up_again(self, env):
        add_lobby(env, roles=(ROLE_1, ROLE_2), next_number=9)
        env.repo.remove_ticket_lobby(LOBBY)
        respond = call(env, channel=env.guild.lobby, prefix="again")
        s = snap(env)
        # 比照 P-02：覆寫舊列並清掉 removed_at，只保留流水號，其餘以新值（預設值）為準
        assert (s["removed_at"], s["next_number"], s["name_prefix"]) == (None, 9, "again")
        assert (s["manager_role_ids"], s["max_open"], s["one_per_user"], s["button_label"]) == ([], None, True, None)
        assert s["ticket_category_id"] == CATEGORY_OWN
        assert respond.call_args.kwargs["embed"].author.name == "已新增私人頻道大廳"
        assert len(env.guild.lobby.sent) == 1


class TestEdit:
    def test_only_prefix_changes(self, env):
        add_lobby(env, roles=(ROLE_1, ROLE_2))
        before = snap(env)
        respond = call(env, channel=env.guild.lobby, prefix="Support")

        after = snap(env)
        assert after["name_prefix"] == "support"
        for key in before:
            if key != "name_prefix":
                assert after[key] == before[key], key
        # 原位更新大廳訊息，沒有另外發新訊息
        assert env.guild.lobby.sent == []
        [edit] = env.guild.lobby.messages[OLD_MESSAGE].edits
        assert edit["embeds"][0].description == "後台寫的說明"
        assert (edit["view"].children[0].label, str(edit["view"].children[0].emoji)) == ("回報", "📮")
        assert respond.call_args.kwargs["embed"].author.name == "已修改私人頻道大廳"
        assert reply_fields(respond)["上限"] == "5"

    def test_one_role_replaces_four(self, env):
        add_lobby(env, roles=(ROLE_1, ROLE_2, ROLE_3, ROLE_4))
        call(env, channel=env.guild.lobby, role1=ROLE_5)
        assert snap(env)["manager_role_ids"] == [ROLE_5]

    def test_clear_max_open(self, env):
        add_lobby(env)
        respond = call(env, channel=env.guild.lobby, clear_max_open=True)
        assert snap(env)["max_open"] is None
        assert reply_fields(respond)["上限"] == "不限"

    def test_clear_roles_removes_overwrites_on_tickets(self, env):
        add_lobby(env, roles=(ROLE_1, ROLE_2))
        env.repo.merge(TicketChannel(channel_id=T1, guild_id=GUILD_ID, creator_id=7, created_at=CREATED, lobby_channel_id=LOBBY))
        ticket = FakeChannel(T1)
        env.guild.channels[T1] = ticket
        respond = call(env, channel=env.guild.lobby, clear_roles=True)
        assert snap(env)["manager_role_ids"] == []
        assert sorted(ticket.permission_calls) == [(ROLE_1, None), (ROLE_2, None)]
        assert reply_fields(respond)["管理身分組"] == "無"

    def test_role_apply_failure_is_reported(self, env):
        add_lobby(env)
        env.repo.merge(TicketChannel(channel_id=T1, guild_id=GUILD_ID, creator_id=7, created_at=CREATED, lobby_channel_id=LOBBY))
        ticket = FakeChannel(T1)
        ticket.fail_permissions = True
        env.guild.channels[T1] = ticket
        respond = call(env, channel=env.guild.lobby, role1=ROLE_2)
        # 大廳設定照存，回覆列出套用失敗的頻道
        assert snap(env)["manager_role_ids"] == [ROLE_2]
        [failure] = [v for k, v in reply_fields(respond).items() if "套用管理身分組失敗" in k]
        assert f"<#{T1}>" in failure

    def test_locked_ticket_gets_view_only_and_saved_json(self, env):
        add_lobby(env, roles=())
        env.repo.merge(
            TicketChannel(
                channel_id=T1,
                guild_id=GUILD_ID,
                creator_id=7,
                created_at=CREATED,
                closed_at=CREATED,
                closer_id=7,
                lobby_channel_id=LOBBY,
                locked_overwrites_json=json.dumps({"member:7": True}),
            )
        )
        ticket = FakeChannel(T1)
        env.guild.channels[T1] = ticket
        call(env, channel=env.guild.lobby, role1=ROLE_1)
        [(rid, overwrite)] = ticket.permission_calls
        assert rid == ROLE_1 and overwrite.send_messages is not True

    def test_message_text_keeps_dashboard_embed(self, env):
        add_lobby(env)
        call(env, channel=env.guild.lobby, message_text="新的文字")
        content = from_json(snap(env)["content_json"])
        assert (content.content, content.embed.description) == ("新的文字", "後台寫的說明")

    def test_one_per_user_can_be_turned_on(self, env):
        add_lobby(env)
        call(env, channel=env.guild.lobby, one_per_user=True)
        assert snap(env)["one_per_user"] is True

    def test_existing_managed_role_is_kept_when_refilled(self, env):
        add_lobby(env, roles=(ROLE_MANAGED,))
        call(env, channel=env.guild.lobby, role1=ROLE_MANAGED, role2=ROLE_1)
        assert snap(env)["manager_role_ids"] == sorted([ROLE_MANAGED, ROLE_1])

    def test_unchanged_emoji_from_dashboard_is_not_rechecked(self, env):
        add_lobby(env, button_emoji=FOREIGN_EMOJI)
        call(env, channel=env.guild.lobby, button_label="開")
        assert (snap(env)["button_label"], snap(env)["button_emoji"]) == ("開", FOREIGN_EMOJI)

    def test_deleted_ticket_category_must_be_reselected(self, env):
        add_lobby(env, ticket_category_id=CATEGORY_OTHER + 999)
        respond = call(env, channel=env.guild.lobby, prefix="x")
        assert_error(respond, "私人頻道分類")
        call(env, channel=env.guild.lobby, ticket_category=env.guild.ticket_category)
        assert snap(env)["ticket_category_id"] == CATEGORY_TICKET

    def test_concurrent_change_is_reported_as_conflict(self, env, monkeypatch):
        add_lobby(env)
        real = env.repo

        def stale(cid):
            current = real.get_ticket_lobby_snapshot(cid)
            return current and {**current, "name_prefix": "stale"}

        monkeypatch.setattr(cmd.sclient, "sqldb", SimpleNamespace(get_ticket_lobby_snapshot=stale))
        respond = call(env, channel=env.guild.lobby, max_open=9)
        assert_error(respond, "其他人修改")
        assert snap(env)["max_open"] == 5

    def test_unreadable_lobby_message_is_reported(self, env):
        add_lobby(env)
        env.guild.lobby.fail_fetch = forbidden()
        respond = call(env, channel=env.guild.lobby, prefix="x")
        assert_error(respond, "Read Message History")
        assert snap(env)["name_prefix"] == "report"


class TestConflictingOptions:
    @pytest.mark.parametrize(
        ("kw", "needle"),
        [
            ({"role1": ROLE_2, "clear_roles": True}, "清空管理身分組"),
            ({"max_open": 3, "clear_max_open": True}, "清空上限"),
            ({"new_channel_name": "x"}, "只能填一個"),
            ({"new_channel_category": "other"}, "新頻道分類"),
        ],
    )
    def test_rejected_without_changes(self, env, kw, needle):
        add_lobby(env)
        before = snap(env)
        if kw.get("new_channel_category") == "other":
            kw = {**kw, "new_channel_category": env.guild.other_category}
        respond = call(env, channel=env.guild.lobby, **kw)
        assert_error(respond, needle)
        assert snap(env) == before
        assert env.guild.lobby.messages[OLD_MESSAGE].edits == []
        assert env.guild.created == []

    def test_no_channel_at_all(self, env):
        assert_error(call(env, prefix="x"), "請填「頻道」")

    def test_all_errors_are_listed(self, env):
        respond = call(env, channel=env.guild.lobby, prefix="!!!", max_open=3, clear_max_open=True, button_label="  ")
        assert_error(respond, "前綴", "清空上限", "按鈕文字")


class TestValidation:
    @pytest.mark.parametrize(
        ("kw", "needle"),
        [
            ({"prefix": "!!!"}, "前綴處理後必須是 1 到 20 個字元"),
            ({"prefix": "a" * 21}, "前綴處理後必須是 1 到 20 個字元"),
            ({"max_open": 0}, "1 到 10000"),
            ({"max_open": 10001}, "1 到 10000"),
            ({"button_label": " "}, "按鈕文字"),
            ({"button_label": "長" * 81}, "80"),
            ({"button_emoji": FOREIGN_EMOJI}, "不屬於這個伺服器"),
            ({"button_emoji": "x" * 101}, "格式不正確"),
            ({"message_text": "  "}, "訊息文字"),
            ({"message_text": "長" * 2001}, "訊息文字"),
            ({"role1": GUILD_ID}, "@everyone"),
            ({"role1": ROLE_MANAGED}, "整合服務"),
            ({"new_channel_name": " ", "ticket_category": "ticket"}, "新頻道名稱"),
        ],
    )
    def test_invalid_values_save_nothing(self, env, kw, needle):
        if kw.get("ticket_category") == "ticket":
            kw = {**kw, "ticket_category": env.guild.ticket_category}
        else:
            kw = {"channel": env.guild.lobby, **kw}
        respond = call(env, **kw)
        assert_error(respond, needle)
        assert snap(env) is None
        assert env.guild.lobby.sent == [] and env.guild.created == []

    def test_unicode_emoji_is_accepted(self, env):
        call(env, channel=env.guild.lobby, button_emoji="🎫")
        assert snap(env)["button_emoji"] == "🎫"

    def test_bot_permission_warning_is_shown(self, env):
        env.guild.own_category.perms = discord.Permissions.all() - discord.Permissions(manage_roles=True)
        respond = call(env, channel=env.guild.lobby)
        assert snap(env) is not None
        assert "Manage Roles" in reply_fields(respond)["注意"]


class TestPermission:
    def _check(self, perms: discord.Permissions):
        [check] = [c for c in cmd.moderation.ticket_setup.checks if "has_guild_permissions" in c.__qualname__]
        return check(SimpleNamespace(guild=object(), author=SimpleNamespace(guild_permissions=perms)))

    def test_requires_guild_manage_channels(self):
        with pytest.raises(commands.MissingPermissions):
            self._check(discord.Permissions(manage_messages=True, manage_roles=True))
        assert self._check(discord.Permissions(manage_channels=True)) is True
