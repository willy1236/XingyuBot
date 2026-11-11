"""伺服器管理後台 P-01：私人頻道大廳與頻道清單（假 Discord，真實 PostgreSQL）。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
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
from starlib.database import TicketChannel, TicketChannelLobby, TicketLobbyManagerRole
from starlib.tickets import bot_permission_issues, lobby_invalid_reason
from starServer.dashboard import tickets

URL = f"/dashboard/guilds/{GUILD_ID}/tickets"
ALL_CHANNEL_PERMS = dict(view_channel=True, send_messages=True, embed_links=True)
ALL_CATEGORY_PERMS = dict(manage_channels=True, manage_roles=True, manage_messages=True)

# 測試資料用不會與真實資料重疊的大 ID，伺服器也用自己的 ID（GUILD_ID 沒有真實資料）
LOBBY_A = 8_900_000_000_000_001
LOBBY_B = 8_900_000_000_000_002
CATEGORY_A = 8_900_000_000_000_101
CATEGORY_B = 8_900_000_000_000_102
CATEGORY_GONE = 8_900_000_000_000_199
MESSAGE_A = 8_900_000_000_000_201
MESSAGE_B = 8_900_000_000_000_202
ROLE_1 = 8_900_000_000_000_301
ROLE_GONE = 8_900_000_000_000_399
T1, T2, T3 = 8_900_000_000_000_401, 8_900_000_000_000_402, 8_900_000_000_000_403
BASE = datetime(2026, 1, 1, tzinfo=UTC)


class FakeChannel:
    def __init__(
        self,
        cid: int,
        name: str,
        type=discord.ChannelType.text,
        position: int = 0,
        category_position: int | None = None,
        **perms,
    ):
        self.id = cid
        self.name = name
        self.type = type
        self.position = position
        self.category = SimpleNamespace(position=category_position) if category_position is not None else None
        self.perms = perms
        self.messages: set[int] = set()
        self.fetch_error: Exception | None = None

    def permissions_for(self, _member):
        return SimpleNamespace(**self.perms)

    async def fetch_message(self, mid: int):
        if self.fetch_error is not None:
            raise self.fetch_error
        if mid not in self.messages:
            raise discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "unknown message")
        return SimpleNamespace(id=mid)


def lobby_channel(cid: int, name: str, position: int = 0, **perms) -> FakeChannel:
    c = FakeChannel(cid, name, position=position, category_position=0, **{**ALL_CHANNEL_PERMS, **perms})
    return c


def category(cid: int, name: str, **perms) -> FakeChannel:
    return FakeChannel(cid, name, type=discord.ChannelType.category, **{**ALL_CATEGORY_PERMS, **perms})


class FakeGuild:
    def __init__(self):
        self.id = GUILD_ID
        self.unavailable = False
        self.me = SimpleNamespace()
        a = lobby_channel(LOBBY_A, "開單", position=1)
        a.messages.add(MESSAGE_A)
        b = lobby_channel(LOBBY_B, "檢舉", position=0)
        b.messages.add(MESSAGE_B)
        self.channels = {
            LOBBY_A: a,
            LOBBY_B: b,
            CATEGORY_A: category(CATEGORY_A, "客服"),
            CATEGORY_B: category(CATEGORY_B, "檢舉區"),
        }
        self.roles = {ROLE_1: SimpleNamespace(id=ROLE_1, name="客服人員")}
        self.members = {7: SimpleNamespace(display_name="小明"), 8: SimpleNamespace(display_name="管理員")}

    def get_channel(self, cid: int):
        return self.channels.get(cid)

    def get_role(self, rid: int):
        return self.roles.get(rid)

    def get_member(self, uid: int):
        return self.members.get(uid)


def add_lobby(repo, cid=LOBBY_A, message=MESSAGE_A, category_id: int | None = CATEGORY_A, guild_id=GUILD_ID, **kw):
    repo.merge(
        TicketChannelLobby(
            channel_id=cid, category_id=1, guild_id=guild_id, message_id=message, ticket_category_id=category_id, **kw
        )
    )


def add_ticket(
    repo, cid: int, lobby: int | None, *, creator=7, minutes=0, closed=False, number=None, guild_id=GUILD_ID
):
    repo.merge(
        TicketChannel(
            channel_id=cid,
            guild_id=guild_id,
            creator_id=creator,
            created_at=BASE.replace(minute=minutes),
            closed_at=BASE.replace(hour=5) if closed else None,
            closer_id=8 if closed else None,
            lobby_channel_id=lobby,
            number=number,
        )
    )


@pytest.fixture
def client(discord_env, dashboard_env, repo, monkeypatch) -> TestClient:  # noqa: F811
    seed_token(repo, dashboard_env.credential_id)
    make_session(repo)
    discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_CHANNELS)]
    monkeypatch.setattr(tickets, "sqldb", repo)
    guild = FakeGuild()
    monkeypatch.setattr(sclient, "bot", fake_bot(guild))
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
    c.cookies.set("dashboard_session", "sid")
    c.repo = repo  # pyright: ignore[reportAttributeAccessIssue]
    c.guild = guild  # pyright: ignore[reportAttributeAccessIssue]
    c.discord_env = discord_env  # pyright: ignore[reportAttributeAccessIssue]
    return c


def get(client) -> dict:
    r = client.get(URL)
    assert r.status_code == 200, r.text
    return r.json()


class TestAccess:
    def test_manage_roles_only_is_forbidden(self, client):
        client.discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_ROLES)]
        assert client.get(URL).status_code == 403

    def test_no_session(self, client):
        client.cookies.clear()
        assert client.get(URL).status_code == 401

    def test_bot_unavailable(self, client, monkeypatch):
        monkeypatch.setattr(sclient, "bot", fake_bot(client.guild, ready=False))
        r = client.get(URL)
        assert (r.status_code, r.json()["error"]) == (503, "bot_unavailable")


class TestLobbies:
    def test_empty(self, client):
        assert get(client) == {"lobbies": [], "unassigned": []}

    def test_legacy_lobby_shows_defaults(self, client):
        """只有測試版欄位的大廳：分類等於 ALTER 回填的值，其餘是預設設定"""
        add_lobby(client.repo)
        [lobby] = get(client)["lobbies"]
        assert lobby["name_prefix"] == "ticket"
        assert lobby["one_per_user"] is True
        assert lobby["max_open"] is None
        assert lobby["manager_roles"] == []
        assert lobby["category"] == {"id": str(CATEGORY_A), "name": "客服", "invalid": False}
        assert lobby["channel"] == {"id": str(LOBBY_A), "name": "開單", "invalid": False}
        assert lobby["invalid_reason"] is None
        assert lobby["permission_issues"] == []
        assert lobby["jump_url"] == f"https://discord.com/channels/{GUILD_ID}/{LOBBY_A}/{MESSAGE_A}"

    def test_settings_and_managers(self, client):
        add_lobby(client.repo, name_prefix="report", one_per_user=False, max_open=5)
        client.repo.merge(TicketLobbyManagerRole(lobby_channel_id=LOBBY_A, role_id=ROLE_1))
        client.repo.merge(TicketLobbyManagerRole(lobby_channel_id=LOBBY_A, role_id=ROLE_GONE))
        [lobby] = get(client)["lobbies"]
        assert (lobby["name_prefix"], lobby["one_per_user"], lobby["max_open"]) == ("report", False, 5)
        assert lobby["manager_roles"] == [
            {"id": str(ROLE_1), "name": "客服人員", "invalid": False},
            {"id": str(ROLE_GONE), "name": None, "invalid": True},
        ]

    def test_removed_and_other_guild_hidden(self, client):
        add_lobby(client.repo, removed_at=BASE)
        add_lobby(client.repo, cid=LOBBY_B, message=MESSAGE_B, category_id=CATEGORY_B, guild_id=GUILD_ID + 1)
        assert get(client)["lobbies"] == []

    def test_sorted_by_channel_position(self, client):
        add_lobby(client.repo)
        add_lobby(client.repo, cid=LOBBY_B, message=MESSAGE_B, category_id=CATEGORY_B)
        assert [x["channel"]["id"] for x in get(client)["lobbies"]] == [str(LOBBY_B), str(LOBBY_A)]

    def test_deleted_channel_sorts_last_and_stays_listed(self, client):
        """大廳頻道被刪（bot 重啟後紀錄也還在）：仍列出並標示失效"""
        add_lobby(client.repo)
        add_lobby(client.repo, cid=LOBBY_B, message=MESSAGE_B, category_id=CATEGORY_B)
        del client.guild.channels[LOBBY_B]
        lobbies = get(client)["lobbies"]
        assert [x["channel"]["id"] for x in lobbies] == [str(LOBBY_A), str(LOBBY_B)]
        assert lobbies[1]["channel"] == {"id": str(LOBBY_B), "name": None, "invalid": True}
        assert lobbies[1]["invalid_reason"] == "channel_deleted"

    def test_missing_permissions(self, client):
        add_lobby(client.repo)
        client.guild.channels[CATEGORY_A].perms["manage_channels"] = False
        client.guild.channels[LOBBY_A].perms["embed_links"] = False
        [lobby] = get(client)["lobbies"]
        assert [(i["permission"], i["target"]) for i in lobby["permission_issues"]] == [
            ("Manage Channels", "category"),
            ("Embed Links", "lobby_channel"),
        ]
        assert lobby["permission_issues"][0]["consequence"] == "無法建立或刪除私人頻道"


class TestTickets:
    def test_grouped_by_lobby_with_status(self, client):
        add_lobby(client.repo)
        add_lobby(client.repo, cid=LOBBY_B, message=MESSAGE_B, category_id=CATEGORY_B)
        for cid in (T1, T2, T3):
            client.guild.channels[cid] = FakeChannel(cid, f"ticket-{cid}")
        add_ticket(client.repo, T2, LOBBY_A, minutes=20, closed=True, number=2)
        add_ticket(client.repo, T1, LOBBY_A, minutes=10, number=1)
        add_ticket(client.repo, T3, LOBBY_B, minutes=5)
        by_id = {x["channel"]["id"]: x for x in get(client)["lobbies"]}
        a = by_id[str(LOBBY_A)]
        assert (a["ticket_count"], a["locked_count"]) == (2, 1)
        assert [t["channel"]["id"] for t in a["tickets"]] == [str(T1), str(T2)]  # 建立時間由舊到新
        open_ticket, locked = a["tickets"]
        assert open_ticket["status"] == "open" and open_ticket["closer"] is None and open_ticket["closed_at"] is None
        assert open_ticket["creator"] == {"id": "7", "name": "小明"}
        assert open_ticket["channel"]["name"] == f"ticket-{T1}"
        assert open_ticket["number"] == 1
        assert locked["status"] == "locked"
        assert locked["closer"] == {"id": "8", "name": "管理員"}
        assert locked["closed_at"] is not None
        assert by_id[str(LOBBY_B)]["ticket_count"] == 1

    def test_unassigned(self, client):
        """lobby_channel_id 為空、指向不存在或已移除的大廳，都列在未歸屬"""
        add_lobby(client.repo)
        add_lobby(client.repo, cid=LOBBY_B, message=MESSAGE_B, category_id=CATEGORY_B, removed_at=BASE)
        for cid in (T1, T2, T3):
            client.guild.channels[cid] = FakeChannel(cid, f"ticket-{cid}")
        add_ticket(client.repo, T1, None, minutes=1)
        add_ticket(client.repo, T2, LOBBY_B, minutes=2)
        add_ticket(client.repo, T3, LOBBY_A, minutes=3)
        body = get(client)
        assert [t["channel"]["id"] for t in body["unassigned"]] == [str(T1), str(T2)]
        assert body["lobbies"][0]["ticket_count"] == 1

    def test_creator_left_has_no_name(self, client):
        client.guild.channels[T1] = FakeChannel(T1, "ticket-x")
        add_ticket(client.repo, T1, None, creator=999)
        [t] = get(client)["unassigned"]
        assert t["creator"] == {"id": "999", "name": None}

    def test_deleted_in_discord_removed_from_list_and_db(self, client):
        add_lobby(client.repo)
        client.guild.channels[T1] = FakeChannel(T1, "ticket-1")
        add_ticket(client.repo, T1, LOBBY_A)
        add_ticket(client.repo, T2, LOBBY_A)  # T2 不在 Discord
        add_ticket(client.repo, T3, None)  # T3 不在 Discord
        body = get(client)
        assert [t["channel"]["id"] for t in body["lobbies"][0]["tickets"]] == [str(T1)]
        assert body["lobbies"][0]["ticket_count"] == 1
        assert body["unassigned"] == []
        assert client.repo.get_ticket_channel(T1) is not None
        assert client.repo.get_ticket_channel(T2) is None
        assert client.repo.get_ticket_channel(T3) is None

    def test_unavailable_guild_returns_503_and_keeps_records(self, client):
        """伺服器 unavailable 時頻道快取是空的：不能當成已刪除而刪紀錄"""
        add_lobby(client.repo)
        add_ticket(client.repo, T1, LOBBY_A)
        client.guild.unavailable = True
        client.guild.channels.clear()
        r = client.get(URL)
        assert (r.status_code, r.json()["error"]) == (503, "guild_unavailable")
        assert client.repo.get_ticket_channel(T1) is not None

    def test_other_guild_untouched(self, client):
        add_ticket(client.repo, T1, None, guild_id=GUILD_ID + 1)  # 另一個伺服器，頻道不在這個 guild 的快取
        assert get(client)["unassigned"] == []
        assert client.repo.get_ticket_channel(T1) is not None


# ====== starlib.tickets ======
def lobby_row(**kw):
    values = dict(channel_id=LOBBY_A, message_id=MESSAGE_A, ticket_category_id=CATEGORY_A)
    return SimpleNamespace(**{**values, **kw})


class TestLobbyInvalidReason:
    def test_valid(self):
        assert asyncio.run(lobby_invalid_reason(FakeGuild(), lobby_row())) is None

    def test_channel_deleted(self):
        assert asyncio.run(lobby_invalid_reason(FakeGuild(), lobby_row(channel_id=1))) == "channel_deleted"

    @pytest.mark.parametrize("category_id", [None, CATEGORY_GONE, LOBBY_A])
    def test_category_deleted_or_not_a_category(self, category_id):
        assert (
            asyncio.run(lobby_invalid_reason(FakeGuild(), lobby_row(ticket_category_id=category_id)))
            == "category_deleted"
        )

    def test_message_deleted(self):
        assert asyncio.run(lobby_invalid_reason(FakeGuild(), lobby_row(message_id=1))) == "message_deleted"

    @pytest.mark.parametrize(
        "error",
        [
            discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "missing access"),
            discord.HTTPException(SimpleNamespace(status=500, reason="Server Error"), "boom"),
        ],
    )
    def test_unreadable_message_is_not_invalid(self, error):
        guild = FakeGuild()
        guild.channels[LOBBY_A].fetch_error = error
        assert asyncio.run(lobby_invalid_reason(guild, lobby_row(message_id=1))) is None

    def test_checks_channel_before_category_before_message(self):
        assert (
            asyncio.run(
                lobby_invalid_reason(FakeGuild(), lobby_row(channel_id=1, ticket_category_id=None, message_id=1))
            )
            == "channel_deleted"
        )
        assert (
            asyncio.run(lobby_invalid_reason(FakeGuild(), lobby_row(ticket_category_id=None, message_id=1)))
            == "category_deleted"
        )


class TestBotPermissionIssues:
    def test_all_granted(self):
        assert bot_permission_issues(FakeGuild(), lobby_row()) == []

    @pytest.mark.parametrize(
        ("holder", "attr", "permission", "target", "consequence"),
        [
            (CATEGORY_A, "manage_channels", "Manage Channels", "category", "無法建立或刪除私人頻道"),
            (CATEGORY_A, "manage_roles", "Manage Roles", "category", "無法設定私人頻道的可見範圍，也無法鎖定、重開"),
            (LOBBY_A, "view_channel", "View Channel", "lobby_channel", "無法發送或更新大廳訊息"),
            (LOBBY_A, "send_messages", "Send Messages", "lobby_channel", "無法發送大廳訊息"),
            (LOBBY_A, "embed_links", "Embed Links", "lobby_channel", "大廳訊息的 embed 無法顯示"),
            (CATEGORY_A, "manage_messages", "Manage Messages", "category", "無法置頂私人頻道的操作訊息"),
        ],
    )
    def test_each_permission(self, holder, attr, permission, target, consequence):
        guild = FakeGuild()
        guild.channels[holder].perms[attr] = False
        [issue] = bot_permission_issues(guild, lobby_row())
        assert (issue.permission, issue.target, issue.consequence) == (permission, target, consequence)

    def test_order_follows_spec_table(self):
        guild = FakeGuild()
        for cid in (CATEGORY_A, LOBBY_A):
            for key in guild.channels[cid].perms:
                guild.channels[cid].perms[key] = False
        assert [i.permission for i in bot_permission_issues(guild, lobby_row())] == [
            "Manage Channels",
            "Manage Roles",
            "View Channel",
            "Send Messages",
            "Embed Links",
            "Manage Messages",
        ]

    def test_skips_missing_locations(self):
        guild = FakeGuild()
        guild.channels[CATEGORY_A].perms["manage_channels"] = False
        assert bot_permission_issues(guild, lobby_row(ticket_category_id=CATEGORY_GONE)) == []
        assert bot_permission_issues(guild, lobby_row(channel_id=1))[0].permission == "Manage Channels"


# ====== repository（真實 PostgreSQL） ======
class TestRepository:
    def test_new_columns_default(self, repo):  # noqa: F811
        """不傳新欄位建立大廳與私人頻道：Python 端預設值寫入（NOT NULL 欄位不會撞）"""
        repo.merge(TicketChannelLobby(channel_id=LOBBY_A, category_id=1, guild_id=GUILD_ID, message_id=MESSAGE_A))
        repo.merge(TicketChannel(channel_id=T1, guild_id=GUILD_ID, creator_id=7, created_at=BASE))
        [(lobby, roles)] = repo.list_guild_ticket_lobbies(GUILD_ID)
        assert (lobby.name_prefix, lobby.one_per_user, lobby.next_number) == ("ticket", True, 1)
        assert (
            lobby.max_open,
            lobby.ticket_category_id,
            lobby.content_json,
            lobby.button_label,
            lobby.button_emoji,
            lobby.removed_at,
        ) == (None,) * 6
        assert roles == []
        [ticket] = repo.list_guild_ticket_channels(GUILD_ID)
        assert (ticket.lobby_channel_id, ticket.number, ticket.locked_overwrites_json) == (None, None, None)

    def test_manager_roles_ordered_and_scoped_to_lobby(self, repo):  # noqa: F811
        add_lobby(repo)
        add_lobby(repo, cid=LOBBY_B, message=MESSAGE_B, category_id=CATEGORY_B)
        for lobby_id, role_id in [(LOBBY_A, 30), (LOBBY_A, 10), (LOBBY_B, 20)]:
            repo.merge(TicketLobbyManagerRole(lobby_channel_id=lobby_id, role_id=role_id))
        assert {lobby.channel_id: roles for lobby, roles in repo.list_guild_ticket_lobbies(GUILD_ID)} == {
            LOBBY_A: [10, 30],
            LOBBY_B: [20],
        }

    def test_delete_ticket_channels(self, repo):  # noqa: F811
        add_ticket(repo, T1, None)
        add_ticket(repo, T2, None)
        repo.delete_ticket_channels([])
        repo.delete_ticket_channels([T1])
        assert repo.get_ticket_channel(T1) is None
        assert repo.get_ticket_channel(T2) is not None

    def test_set_ticket_channel_lobby(self, repo):  # noqa: F811
        add_ticket(repo, T1, None)
        repo.set_ticket_channel_lobby(T1, LOBBY_A)
        assert repo.get_ticket_channel(T1).lobby_channel_id == LOBBY_A
        assert T1 not in {t.channel_id for t in repo.list_unassigned_ticket_channels()}


class TestLobbyWriteRepository:
    """P-02 的大廳寫入：真實 PostgreSQL"""

    VALUES = dict(
        channel_id=LOBBY_A,
        guild_id=GUILD_ID,
        message_id=MESSAGE_A,
        category_id=5,
        ticket_category_id=CATEGORY_A,
        name_prefix="report",
        one_per_user=False,
        max_open=3,
        content_json='{"content": "hi"}',
        button_label="開單",
        button_emoji="🎫",
    )

    def test_insert_and_snapshot(self, repo):  # noqa: F811
        assert repo.insert_ticket_lobby(dict(self.VALUES), [30, 10, 10])
        snap = repo.get_ticket_lobby_snapshot(LOBBY_A)
        assert snap is not None
        assert (snap["name_prefix"], snap["one_per_user"], snap["max_open"], snap["next_number"]) == ("report", False, 3, 1)
        assert (snap["button_label"], snap["button_emoji"], snap["removed_at"]) == ("開單", "🎫", None)
        assert snap["manager_role_ids"] == [10, 30]
        assert repo.get_ticket_lobby_snapshot(LOBBY_B) is None

    def test_insert_rejects_active_lobby_and_writes_nothing(self, repo):  # noqa: F811
        add_lobby(repo, name_prefix="old")
        assert not repo.insert_ticket_lobby(dict(self.VALUES), [10])
        snap = repo.get_ticket_lobby_snapshot(LOBBY_A)
        assert snap["name_prefix"] == "old"
        assert snap["manager_role_ids"] == []

    def test_insert_overwrites_removed_lobby_keeping_next_number(self, repo):  # noqa: F811
        add_lobby(repo, next_number=7, name_prefix="old")
        repo.set_lobby_manager_roles(LOBBY_A, [99])
        assert repo.remove_ticket_lobby(LOBBY_A)
        assert repo.insert_ticket_lobby(dict(self.VALUES, message_id=MESSAGE_B), [10])
        snap = repo.get_ticket_lobby_snapshot(LOBBY_A)
        assert (snap["name_prefix"], snap["message_id"], snap["removed_at"], snap["next_number"]) == ("report", MESSAGE_B, None, 7)
        assert snap["manager_role_ids"] == [10]
        assert [lobby.channel_id for lobby, _ in repo.list_guild_ticket_lobbies(GUILD_ID)] == [LOBBY_A]

    def test_update_if_matches_original(self, repo):  # noqa: F811
        add_lobby(repo, name_prefix="old", max_open=None)
        repo.set_lobby_manager_roles(LOBBY_A, [10])
        ok = repo.update_ticket_lobby_if(
            LOBBY_A, {"name_prefix": "old", "max_open": None}, {"name_prefix": "new", "max_open": 2}, [20, 30]
        )
        assert ok
        snap = repo.get_ticket_lobby_snapshot(LOBBY_A)
        assert (snap["name_prefix"], snap["max_open"], snap["manager_role_ids"]) == ("new", 2, [20, 30])

    def test_update_if_conflict_writes_nothing(self, repo):  # noqa: F811
        add_lobby(repo, name_prefix="changed")
        repo.set_lobby_manager_roles(LOBBY_A, [10])
        assert not repo.update_ticket_lobby_if(LOBBY_A, {"name_prefix": "old"}, {"name_prefix": "new"}, [20])
        snap = repo.get_ticket_lobby_snapshot(LOBBY_A)
        assert (snap["name_prefix"], snap["manager_role_ids"]) == ("changed", [10])

    def test_update_if_ignores_removed_lobby(self, repo):  # noqa: F811
        add_lobby(repo)
        repo.remove_ticket_lobby(LOBBY_A)
        assert not repo.update_ticket_lobby_if(LOBBY_A, {}, {"name_prefix": "new"})

    def test_remove_hides_lobby_and_startup_load(self, repo):  # noqa: F811
        add_lobby(repo)
        add_lobby(repo, cid=LOBBY_B, message=MESSAGE_B)
        assert repo.remove_ticket_lobby(LOBBY_A)
        assert not repo.remove_ticket_lobby(LOBBY_A)
        assert [lobby.channel_id for lobby, _ in repo.list_guild_ticket_lobbies(GUILD_ID)] == [LOBBY_B]
        assert LOBBY_A not in {lobby.channel_id for lobby in repo.get_all_ticket_lobbys()}
        assert LOBBY_B in {lobby.channel_id for lobby in repo.get_all_ticket_lobbys()}

    def test_remove_unassigns_only_its_tickets_in_the_same_transaction(self, repo):  # noqa: F811
        add_lobby(repo)
        add_ticket(repo, T1, LOBBY_A)
        add_ticket(repo, T2, LOBBY_B)
        assert repo.remove_ticket_lobby(LOBBY_A)
        assert repo.get_ticket_channel(T1).lobby_channel_id is None
        assert repo.get_ticket_channel(T2).lobby_channel_id == LOBBY_B

    def test_remove_already_removed_changes_nothing(self, repo):  # noqa: F811
        add_lobby(repo)
        repo.remove_ticket_lobby(LOBBY_A)
        add_ticket(repo, T1, LOBBY_A)  # 已移除的大廳不會再動到頻道
        assert not repo.remove_ticket_lobby(LOBBY_A)
        assert repo.get_ticket_channel(T1).lobby_channel_id == LOBBY_A

    def test_move_lobby_keeps_number_and_tickets(self, repo):  # noqa: F811
        add_lobby(repo, next_number=5, name_prefix="old")
        repo.set_lobby_manager_roles(LOBBY_A, [10])
        add_ticket(repo, T1, LOBBY_A)
        values = {k: v for k, v in self.VALUES.items() if k not in ("channel_id", "guild_id")}
        assert repo.move_ticket_lobby(LOBBY_A, LOBBY_B, values, [20])
        assert repo.get_ticket_lobby_snapshot(LOBBY_A) is None
        snap = repo.get_ticket_lobby_snapshot(LOBBY_B)
        assert (snap["name_prefix"], snap["next_number"], snap["manager_role_ids"]) == ("report", 5, [20])
        assert repo.get_ticket_channel(T1).lobby_channel_id == LOBBY_B
        assert repo.list_lobby_ticket_channels(LOBBY_A) == []

    def test_move_lobby_rejects_active_target(self, repo):  # noqa: F811
        add_lobby(repo, name_prefix="old")
        add_lobby(repo, cid=LOBBY_B, message=MESSAGE_B, name_prefix="other")
        assert not repo.move_ticket_lobby(LOBBY_A, LOBBY_B, {"name_prefix": "new"}, [])
        assert repo.get_ticket_lobby_snapshot(LOBBY_A)["name_prefix"] == "old"
        assert repo.get_ticket_lobby_snapshot(LOBBY_B)["name_prefix"] == "other"

    def test_move_lobby_replaces_removed_target(self, repo):  # noqa: F811
        add_lobby(repo, next_number=5)
        add_lobby(repo, cid=LOBBY_B, message=MESSAGE_B, next_number=99)
        repo.set_lobby_manager_roles(LOBBY_B, [77])
        repo.remove_ticket_lobby(LOBBY_B)
        assert repo.move_ticket_lobby(LOBBY_A, LOBBY_B, {"name_prefix": "new"}, [10])
        snap = repo.get_ticket_lobby_snapshot(LOBBY_B)
        assert (snap["next_number"], snap["removed_at"], snap["manager_role_ids"]) == (5, None, [10])

    def test_move_lobby_rejects_removed_source(self, repo):  # noqa: F811
        add_lobby(repo)
        repo.remove_ticket_lobby(LOBBY_A)
        assert not repo.move_ticket_lobby(LOBBY_A, LOBBY_B, {}, [])

    def test_locked_overwrites_roundtrip(self, repo):  # noqa: F811
        add_ticket(repo, T1, LOBBY_A, closed=True)
        add_ticket(repo, T2, LOBBY_A)
        repo.set_ticket_locked_overwrites({T1: '{"role:1": true}'})
        by_id = {t.channel_id: t for t in repo.list_lobby_ticket_channels(LOBBY_A)}
        assert by_id[T1].locked_overwrites_json == '{"role:1": true}'
        assert by_id[T2].locked_overwrites_json is None
