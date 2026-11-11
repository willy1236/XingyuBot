"""伺服器管理後台 R-01：反應身分組一覽、失效標示與 bot 權限警告（假 Discord，真實 PostgreSQL）。"""

from __future__ import annotations

from types import SimpleNamespace

import discord
import pytest
from fastapi.testclient import TestClient
from test_dashboard_auth import dashboard_env, make_app, make_session  # noqa: F401  (fixture 與 helper)
from test_dashboard_guilds import MANAGE_CHANNELS, MANAGE_ROLES, g, seed_token
from test_dashboard_guilds import discord as discord_env  # noqa: F401  (fixture)
from test_dashboard_notifies import GUILD_ID, fake_bot
from test_identity import repo  # noqa: F401

from starlib import sclient
from starlib.database import ReactionRoleMessage, ReactionRoleOption
from starlib.reaction_roles import bot_permission_issues, emoji_valid, role_issue
from starServer.dashboard import reaction_roles

URL = f"/dashboard/guilds/{GUILD_ID}/reaction-roles"
ALL_PERMS = dict(view_channel=True, send_messages=True, embed_links=True, read_message_history=True)

BOT_TOP = 10
ROLE_OK = 3001
ROLE_ABOVE = 3002
ROLE_MANAGED = 3003
ROLE_GONE = 3999
EVERYONE = GUILD_ID


class FakeRole:
    def __init__(self, rid: int, name: str, position: int, managed: bool = False):
        self.id = rid
        self.name = name
        self.position = position
        self.managed = managed

    def is_default(self) -> bool:
        return self.id == EVERYONE

    def __ge__(self, other: FakeRole) -> bool:
        return self.position >= other.position


class FakeChannel:
    def __init__(self, cid: int, name: str, position: int, category_position: int | None = None, **perms):
        self.id = cid
        self.name = name
        self.position = position
        self.category = SimpleNamespace(position=category_position) if category_position is not None else None
        self.perms = {**ALL_PERMS, **perms}
        self.messages: dict[int, discord.Message | SimpleNamespace] = {}
        self.forbidden = False

    def permissions_for(self, _member):
        return SimpleNamespace(**self.perms)

    async def fetch_message(self, mid: int):
        if getattr(self, "fetch_error", None) is not None:
            raise self.fetch_error
        if self.forbidden:
            raise discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "missing access")
        if mid not in self.messages:
            raise discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "unknown message")
        return self.messages[mid]


def msg(content: str = "", embeds=()):
    return SimpleNamespace(content=content, embeds=list(embeds))


class FakeGuild:
    def __init__(self):
        self.id = GUILD_ID
        self.me = SimpleNamespace(top_role=FakeRole(1, "bot", BOT_TOP), guild_permissions=SimpleNamespace(manage_roles=True))
        self.roles = {
            ROLE_OK: FakeRole(ROLE_OK, "活動", 5),
            ROLE_ABOVE: FakeRole(ROLE_ABOVE, "管理", BOT_TOP),
            ROLE_MANAGED: FakeRole(ROLE_MANAGED, "整合", 2, managed=True),
            EVERYONE: FakeRole(EVERYONE, "@everyone", 0),
        }
        self.channels = {
            500: FakeChannel(500, "公告", position=1, category_position=0),
            501: FakeChannel(501, "身分組", position=0, category_position=0),
            502: FakeChannel(502, "閒聊", position=0, category_position=1),
        }
        self.emojis = {700000000000001}

    def get_channel(self, cid: int):
        return self.channels.get(cid)

    def get_role(self, rid: int):
        return self.roles.get(rid)

    def get_emoji(self, eid: int):
        return SimpleNamespace(id=eid) if eid in self.emojis else None


class FakeRepo:
    """不碰 DB 的假 repository：本機測試庫未執行任務卡的 ALTER，依 position 排序的 SQL 不在這裡驗證。"""

    def __init__(self):
        self.rows: list[tuple[ReactionRoleMessage, list[ReactionRoleOption]]] = []

    def list_guild_reaction_roles(self, guild_id: int):
        return [(m, opts) for m, opts in self.rows if m.guild_id == guild_id]


@pytest.fixture
def client(discord_env, dashboard_env, repo, monkeypatch) -> TestClient:  # noqa: F811
    seed_token(repo, dashboard_env.credential_id)
    make_session(repo)
    discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_ROLES)]
    fake_repo = FakeRepo()
    monkeypatch.setattr(reaction_roles, "sqldb", fake_repo)
    guild = FakeGuild()
    monkeypatch.setattr(sclient, "bot", fake_bot(guild))
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
    c.cookies.set("dashboard_session", "sid")
    c.repo = fake_repo  # pyright: ignore[reportAttributeAccessIssue]
    c.guild = guild  # pyright: ignore[reportAttributeAccessIssue]
    c.discord_env = discord_env  # pyright: ignore[reportAttributeAccessIssue]
    return c


def add_message(client, mid: int, cid: int = 501, *, buttons=((ROLE_OK, "活動", None),), content: str | None = "請選身分組", guild_id=GUILD_ID):
    options = [
        ReactionRoleOption(message_id=mid, role_id=rid, title=title, description=None, emoji=emoji, style=1, position=position)
        for position, (rid, title, emoji) in enumerate(buttons)
    ]
    client.repo.rows.append((ReactionRoleMessage(guild_id=guild_id, channel_id=cid, message_id=mid), options))
    channel = client.guild.channels.get(cid)
    if channel is not None and content is not None:
        channel.messages[mid] = msg(content)


def get(client) -> list[dict]:
    r = client.get(URL)
    assert r.status_code == 200, r.text
    return r.json()["messages"]


# ====== 端點 ======
class TestList:
    def test_empty(self, client):
        assert get(client) == []

    def test_item_fields(self, client):
        add_message(client, 900, buttons=[(ROLE_OK, "活動", "🎉")])
        [item] = get(client)
        assert item["message_id"] == "900"
        assert item["channel"] == {"id": "501", "name": "身分組", "invalid": False}
        assert item["invalid"] is False
        assert item["summary"] == "請選身分組"
        assert item["jump_url"] == f"https://discord.com/channels/{GUILD_ID}/501/900"
        assert item["buttons"] == [
            {"role": {"id": str(ROLE_OK), "name": "活動", "invalid": False}, "title": "活動", "emoji": "🎉", "emoji_invalid": False, "style": 1}
        ]
        assert item["permission_issues"] == []

    def test_only_this_guild(self, client):
        add_message(client, 900)
        add_message(client, 901, guild_id=GUILD_ID + 1)
        assert [i["message_id"] for i in get(client)] == ["900"]

    def test_sorted_by_channel_position_then_message_time(self, client):
        # 閒聊(分類 1)、公告(分類 0 位置 1)、身分組(分類 0 位置 0)；同頻道內訊息 ID 小的在前
        add_message(client, 905, cid=502)
        add_message(client, 904, cid=500)
        add_message(client, 903, cid=501)
        add_message(client, 902, cid=501)
        assert [i["message_id"] for i in get(client)] == ["902", "903", "904", "905"]

    def test_buttons_keep_repository_order(self, client):
        add_message(client, 900, buttons=[(ROLE_ABOVE, "第一", None), (ROLE_MANAGED, "第二", None), (ROLE_OK, "第三", None)])
        assert [b["title"] for b in get(client)[0]["buttons"]] == ["第一", "第二", "第三"]

    def test_summary_truncated_and_embed_fallback(self, client):
        add_message(client, 900, content="字" * 150)
        add_message(client, 901, content="")
        client.guild.channels[501].messages[901] = msg("", embeds=[SimpleNamespace(title="嵌入標題", description="內文")])
        items = {i["message_id"]: i for i in get(client)}
        assert items["900"]["summary"] == "字" * 100 + "…"
        assert items["901"]["summary"] == "嵌入標題"


class TestInvalid:
    def test_role_deleted_marks_only_that_button(self, client):
        add_message(client, 900, buttons=[(ROLE_OK, "好", None), (ROLE_GONE, "壞", None)])
        buttons = get(client)[0]["buttons"]
        assert buttons[0]["role"]["invalid"] is False
        assert buttons[1]["role"] == {"id": str(ROLE_GONE), "name": None, "invalid": True}

    @pytest.mark.parametrize("rid", [ROLE_ABOVE, ROLE_MANAGED, EVERYONE])
    def test_role_not_assignable_marks_button(self, client, rid):
        add_message(client, 900, buttons=[(rid, "按鈕", None)])
        assert get(client)[0]["buttons"][0]["role"]["invalid"] is True

    def test_custom_emoji_deleted(self, client):
        add_message(client, 900, buttons=[(ROLE_OK, "有", "<:ok:700000000000001>"), (ROLE_ABOVE, "無", "<:gone:700000000000002>")])
        client.guild.roles[ROLE_ABOVE].position = 1  # 讓身分組有效，只剩 emoji 判斷
        flags = [b["emoji_invalid"] for b in get(client)[0]["buttons"]]
        assert flags == [False, True]

    def test_message_deleted_marks_whole_message(self, client):
        add_message(client, 900, content=None)
        [item] = get(client)
        assert item["invalid"] is True
        assert item["channel"]["invalid"] is False
        assert item["summary"] is None

    def test_channel_deleted_marks_whole_message(self, client):
        add_message(client, 900, cid=999)
        [item] = get(client)
        assert item["invalid"] is True
        assert item["channel"] == {"id": "999", "name": None, "invalid": True}
        assert item["jump_url"].endswith("/999/900")

    def test_deleted_channel_sorted_last(self, client):
        add_message(client, 900, cid=999)
        add_message(client, 901, cid=502)
        assert [i["message_id"] for i in get(client)] == ["901", "900"]

    def test_unreadable_message_is_not_marked_invalid(self, client):
        add_message(client, 900)
        client.guild.channels[501].forbidden = True
        [item] = get(client)
        assert item["invalid"] is False
        assert item["summary"] is None


class TestPermissionIssues:
    def test_missing_manage_roles(self, client):
        add_message(client, 900)
        client.guild.me.guild_permissions.manage_roles = False
        assert get(client)[0]["permission_issues"] == [
            {"permission": "Manage Roles", "scope": "guild", "consequence": "按下按鈕無法給予或移除身分組"}
        ]

    def test_missing_channel_permissions_in_order(self, client):
        add_message(client, 900)
        client.guild.channels[501].perms.update(view_channel=False, send_messages=False, embed_links=False, read_message_history=False)
        issues = get(client)[0]["permission_issues"]
        assert [(i["permission"], i["scope"]) for i in issues] == [
            ("View Channel", "channel"),
            ("Send Messages", "channel"),
            ("Embed Links", "channel"),
            ("Read Message History", "channel"),
        ]
        assert all(i["consequence"] for i in issues)

    def test_only_checks_own_channel(self, client):
        add_message(client, 900, cid=501)
        add_message(client, 901, cid=502)
        client.guild.channels[502].perms["embed_links"] = False
        items = {i["message_id"]: i for i in get(client)}
        assert items["900"]["permission_issues"] == []
        assert [i["permission"] for i in items["901"]["permission_issues"]] == ["Embed Links"]

    def test_deleted_channel_only_checks_guild_level(self, client):
        add_message(client, 900, cid=999)
        client.guild.me.guild_permissions.manage_roles = False
        assert [i["permission"] for i in get(client)[0]["permission_issues"]] == ["Manage Roles"]


class TestAccess:
    def test_manage_roles_only_can_enter(self, client):
        assert client.get(URL).status_code == 200

    def test_manage_channels_only_is_403(self, client):
        client.discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_CHANNELS)]
        r = client.get(URL)
        assert r.status_code == 403
        assert r.json()["error"] == "no_permission"

    def test_no_permission_is_403(self, client):
        client.discord_env.guilds = [g(str(GUILD_ID), "guild", 0)]
        assert client.get(URL).status_code == 403

    def test_unauthenticated_is_401(self, client):
        client.cookies.clear()
        assert client.get(URL).status_code == 401


# ====== starlib 共用規則 ======
class TestRoleIssue:
    def test_ok(self):
        guild = FakeGuild()
        assert role_issue(guild, guild.roles[ROLE_OK]) is None

    def test_missing(self):
        assert role_issue(FakeGuild(), None) == "身分組不存在"

    @pytest.mark.parametrize("rid", [EVERYONE, ROLE_MANAGED])
    def test_everyone_or_managed(self, rid):
        guild = FakeGuild()
        assert "@everyone" in role_issue(guild, guild.roles[rid])

    def test_not_lower_than_bot(self):
        guild = FakeGuild()
        assert "不低於" in role_issue(guild, guild.roles[ROLE_ABOVE])
        guild.roles[ROLE_ABOVE].position = BOT_TOP + 5
        assert "不低於" in role_issue(guild, guild.roles[ROLE_ABOVE])
        guild.roles[ROLE_ABOVE].position = BOT_TOP - 1
        assert role_issue(guild, guild.roles[ROLE_ABOVE]) is None


class TestEmojiValid:
    def test_none_empty_and_unicode(self):
        guild = FakeGuild()
        assert emoji_valid(guild, None)
        assert emoji_valid(guild, "")
        assert emoji_valid(guild, "🎉")

    def test_custom(self):
        guild = FakeGuild()
        assert emoji_valid(guild, "<:ok:700000000000001>")
        assert emoji_valid(guild, "<a:ok:700000000000001>")
        assert not emoji_valid(guild, "<:gone:700000000000002>")


class TestBotPermissionIssues:
    def test_all_present(self):
        guild = FakeGuild()
        assert bot_permission_issues(guild, guild.channels[501]) == []

    def test_none_channel_checks_guild_only(self):
        guild = FakeGuild()
        guild.me.guild_permissions.manage_roles = False
        assert [i.permission for i in bot_permission_issues(guild, None)] == ["Manage Roles"]
