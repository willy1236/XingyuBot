"""伺服器管理後台 P-02：新增、修改、移除私人頻道大廳（假 Discord，真實 PostgreSQL）。"""

from __future__ import annotations

from types import SimpleNamespace

import discord
import pytest
from fastapi.testclient import TestClient
from test_dashboard_auth import FRONTEND, USER_ID, dashboard_env, make_app, make_session  # noqa: F401  (fixture 與 helper)
from test_dashboard_guilds import MANAGE_CHANNELS, MANAGE_ROLES, g, seed_token
from test_dashboard_guilds import discord as discord_env  # noqa: F401  (fixture)
from test_dashboard_notifies import GUILD_ID
from test_identity import repo  # noqa: F401
from test_ticket_lobby import (
    CATEGORY_OWN,
    CATEGORY_TICKET,
    LOBBY_A,
    LOBBY_NEW,
    OLD_MESSAGE,
    ROLE_1,
    ROLE_2,
    T1,
    FakeBot,
    FakeChannel,
    FakeMessage,
    add_ticket,
)
from test_ticket_lobby import FakeGuild as BaseGuild

from starDiscord import ticket_lobby
from starlib import sclient
from starlib.database import TicketChannelLobby
from starlib.message_content import MessageContent, from_json, to_json
from starServer.dashboard import tickets

URL = f"/dashboard/guilds/{GUILD_ID}/tickets"
LOBBIES = f"{URL}/lobbies"
ACTOR_ID = int(USER_ID)
EVERYONE = 8_800_000_000_000_060
ROLE_MANAGED = 8_800_000_000_000_061
EMOJI_OK = "<:ok:700000000000001>"
EMOJI_GONE = "<:gone:700000000000002>"
ALL_PERMS = dict(
    manage_channels=True,
    manage_roles=True,
    manage_messages=True,
    view_channel=True,
    read_message_history=True,
    send_messages=True,
    embed_links=True,
)


class FakeRole:
    def __init__(self, rid: int, name: str, position: int, managed: bool = False):
        self.id = rid
        self.name = name
        self.position = position
        self.managed = managed
        self.color = SimpleNamespace(value=0)

    def is_default(self) -> bool:
        return self.id == EVERYONE


class Channel(FakeChannel):
    """帶名稱、位置與 bot 權限的頻道"""

    def __init__(self, cid, name="頻道", kind=discord.ChannelType.text, category_id=CATEGORY_OWN, **perms):
        super().__init__(cid, kind=kind, category_id=category_id)
        self.name = name
        self.position = 0
        self.category = SimpleNamespace(position=0, name="分類") if kind == discord.ChannelType.text else None
        self.perms = {**ALL_PERMS, **perms}

    def permissions_for(self, _member):
        return SimpleNamespace(**self.perms)


class FakeGuild(BaseGuild):
    def __init__(self):
        super().__init__()
        self.id = GUILD_ID
        self.unavailable = False
        self.lobby = Channel(LOBBY_A, "開單")
        self.ticket_category = Channel(CATEGORY_TICKET, "客服", kind=discord.ChannelType.category)
        self.channels = {self.lobby.id: self.lobby, self.ticket_category.id: self.ticket_category}
        self.roles_map = {
            EVERYONE: FakeRole(EVERYONE, "@everyone", 0),
            ROLE_1: FakeRole(ROLE_1, "客服人員", 5),
            ROLE_2: FakeRole(ROLE_2, "管理組", 6),
            ROLE_MANAGED: FakeRole(ROLE_MANAGED, "整合", 2, managed=True),
        }
        self.roles = list(self.roles_map.values())  # pyright: ignore[reportIncompatibleVariableOverride]
        self.actor = SimpleNamespace(id=ACTOR_ID, display_name="管理員", name="admin")
        self.emojis = [SimpleNamespace(id=700000000000001, name="ok", animated=False, __str__=lambda self: EMOJI_OK)]

    @property
    def text_channels(self):
        return [c for c in self.channels.values() if c.type == discord.ChannelType.text]

    @property
    def categories(self):
        return [c for c in self.channels.values() if c.type == discord.ChannelType.category]

    def get_role(self, rid):
        return self.roles_map.get(rid)

    def get_member(self, uid):
        return self.actor if uid == ACTOR_ID else None

    def get_emoji(self, eid):
        return SimpleNamespace(id=eid) if any(e.id == eid for e in self.emojis) else None

    async def create_text_channel(self, name, **kwargs):
        c = Channel(LOBBY_NEW, name)
        self.channels[c.id] = c
        self.created.append((name, kwargs))
        return c


class WebBot(FakeBot):
    def __init__(self, guild):
        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        super().__init__()
        pool = ThreadPoolExecutor(max_workers=1)
        self._guild = guild
        self.is_ready = lambda: True
        self.submit = lambda coro: pool.submit(asyncio.run, coro)

    def get_guild(self, gid):
        return self._guild if gid == GUILD_ID else None


@pytest.fixture
def client(discord_env, dashboard_env, repo, monkeypatch) -> TestClient:  # noqa: F811
    seed_token(repo, dashboard_env.credential_id)
    make_session(repo)
    discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_CHANNELS)]
    monkeypatch.setattr(tickets, "sqldb", repo)
    monkeypatch.setattr(ticket_lobby, "sqldb", repo)
    guild = FakeGuild()
    bot = WebBot(guild)
    monkeypatch.setattr(sclient, "bot", bot)
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False, headers={"Origin": FRONTEND})
    c.cookies.set("dashboard_session", "sid")
    c.repo = repo  # pyright: ignore[reportAttributeAccessIssue]
    c.guild = guild  # pyright: ignore[reportAttributeAccessIssue]
    c.bot = bot  # pyright: ignore[reportAttributeAccessIssue]
    c.discord_env = discord_env  # pyright: ignore[reportAttributeAccessIssue]
    return c


def message(text: str = "請按按鈕") -> dict:
    return {"content": None, "embed": {"description": text}}


def body(**kw) -> dict:
    base = {
        "lobby_channel": {"kind": "existing", "id": str(LOBBY_A)},
        "ticket_category_id": str(CATEGORY_TICKET),
        "manager_role_ids": [str(ROLE_1)],
        "name_prefix": "Report Case",
        "one_per_user": True,
        "max_open": None,
        "message": message(),
        "button_label": "開單",
        "button_emoji": None,
    }
    base.update(kw)
    return base


def fields(r) -> set[str]:
    assert r.status_code == 400, r.text
    assert r.json()["error"] == "invalid_request"
    return {f["path"] for f in r.json()["fields"]}


def add_lobby(client, **kw):
    """已存在的大廳與它的訊息，管理身分組 ROLE_1"""
    client.guild.lobby.messages[OLD_MESSAGE] = FakeMessage(OLD_MESSAGE)
    client.repo.merge(
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
    client.repo.set_lobby_manager_roles(LOBBY_A, [ROLE_1])
    return client.guild.lobby.messages[OLD_MESSAGE]


class TestAccess:
    def test_manage_roles_only_is_forbidden(self, client):
        client.discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_ROLES)]
        assert client.post(LOBBIES, json=body()).status_code == 403
        assert client.get(f"{URL}/options").status_code == 403
        assert client.put(f"{LOBBIES}/{LOBBY_A}", json={}).status_code == 403
        assert client.request("DELETE", f"{LOBBIES}/{LOBBY_A}", json={}).status_code == 403

    def test_no_session(self, client):
        client.cookies.clear()
        assert client.post(LOBBIES, json=body()).status_code == 401


class TestOptions:
    def test_payload(self, client):
        client.guild.ticket_category.perms["manage_roles"] = False
        r = client.get(f"{URL}/options")
        assert r.status_code == 200
        data = r.json()
        assert [c["id"] for c in data["channels"]] == [str(LOBBY_A)]
        assert [c["id"] for c in data["categories"]] == [str(CATEGORY_TICKET)]
        assert [i["permission"] for i in data["categories"][0]["permission_issues"]] == ["Manage Roles"]
        roles = {r["id"]: r for r in data["roles"]}
        assert roles[str(EVERYONE)]["disabled_reason"] is not None
        assert roles[str(ROLE_MANAGED)]["disabled_reason"] is not None
        assert roles[str(ROLE_1)]["disabled_reason"] is None
        assert data["emojis"][0]["id"] == "700000000000001"

    def test_unavailable(self, client):
        client.guild.unavailable = True
        r = client.get(f"{URL}/options")
        assert (r.status_code, r.json()["error"]) == (503, "guild_unavailable")


class TestGetLobby:
    def test_default_content_when_none_stored(self, client):
        add_lobby(client)
        r = client.get(f"{LOBBIES}/{LOBBY_A}")
        assert r.status_code == 200
        data = r.json()
        assert data["content"]["embed"]["description"] == "點擊下方按鈕以建立私人頻道"
        assert data["original"]["content_json"] is None
        assert data["manager_role_ids"] == [str(ROLE_1)]
        assert data["original"]["manager_role_ids"] == [str(ROLE_1)]
        assert data["invalid_reason"] is None

    def test_stored_content(self, client):
        add_lobby(client, content_json=to_json(MessageContent(content="存下的")), button_label="開單")
        data = client.get(f"{LOBBIES}/{LOBBY_A}").json()
        assert data["content"]["content"] == "存下的"
        assert data["button_label"] == "開單"
        assert data["original"]["content_json"] == to_json(MessageContent(content="存下的"))

    def test_invalid_reason_when_channel_deleted(self, client):
        add_lobby(client)
        del client.guild.channels[LOBBY_A]
        assert client.get(f"{LOBBIES}/{LOBBY_A}").json()["invalid_reason"] == "channel_deleted"

    def test_not_found_and_removed(self, client):
        assert client.get(f"{LOBBIES}/{LOBBY_A}").status_code == 404
        add_lobby(client)
        client.repo.remove_ticket_lobby(LOBBY_A)
        assert client.get(f"{LOBBIES}/{LOBBY_A}").status_code == 404

    def test_other_guild_is_not_found(self, client):
        client.repo.merge(TicketChannelLobby(channel_id=LOBBY_A, category_id=1, guild_id=GUILD_ID + 1, message_id=1))
        assert client.get(f"{LOBBIES}/{LOBBY_A}").status_code == 404

    def test_unavailable(self, client):
        add_lobby(client)
        client.guild.unavailable = True
        assert client.get(f"{LOBBIES}/{LOBBY_A}").status_code == 503


class TestCreate:
    def test_creates_lobby_with_normalized_prefix(self, client):
        r = client.post(LOBBIES, json=body())
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["channel_id"] == str(LOBBY_A)
        assert data["failures"] == []
        snap = client.repo.get_ticket_lobby_snapshot(LOBBY_A)
        assert (snap["name_prefix"], snap["manager_role_ids"], snap["button_label"]) == (
            "report-case",
            [ROLE_1],
            "開單",
        )
        assert from_json(snap["content_json"]).embed.description == "請按按鈕"
        [(sent, kwargs)] = client.guild.lobby.sent
        assert kwargs["view"].children[0].custom_id == f"create_ticket_{LOBBY_A}"
        assert client.bot.views[0][0] == sent.id

    def test_two_lobbies_with_same_prefix_and_different_roles(self, client):
        other = Channel(LOBBY_NEW, "檢舉")
        client.guild.channels[LOBBY_NEW] = other
        assert client.post(LOBBIES, json=body(manager_role_ids=[str(ROLE_1)])).status_code == 200
        r = client.post(
            LOBBIES,
            json=body(lobby_channel={"kind": "existing", "id": str(LOBBY_NEW)}, manager_role_ids=[str(ROLE_2)]),
        )
        assert r.status_code == 200
        assert client.repo.get_ticket_lobby_snapshot(LOBBY_A)["manager_role_ids"] == [ROLE_1]
        assert client.repo.get_ticket_lobby_snapshot(LOBBY_NEW)["manager_role_ids"] == [ROLE_2]
        assert client.repo.get_ticket_lobby_snapshot(LOBBY_NEW)["name_prefix"] == "report-case"

    def test_new_channel(self, client):
        r = client.post(
            LOBBIES, json=body(lobby_channel={"kind": "new", "name": "新大廳", "category_id": str(CATEGORY_TICKET)})
        )
        assert r.status_code == 200, r.text
        assert r.json()["channel_id"] == str(LOBBY_NEW)
        [(name, kwargs)] = client.guild.created
        assert name == "新大廳"
        assert "透過後台" in kwargs["reason"]

    def test_same_channel_cannot_be_two_lobbies(self, client):
        assert client.post(LOBBIES, json=body()).status_code == 200
        assert fields(client.post(LOBBIES, json=body())) == {"lobby_channel"}
        assert len(client.guild.lobby.sent) == 1

    def test_removed_lobby_channel_can_be_set_again(self, client):
        add_lobby(client, next_number=4)
        client.repo.remove_ticket_lobby(LOBBY_A)
        assert client.post(LOBBIES, json=body()).status_code == 200
        snap = client.repo.get_ticket_lobby_snapshot(LOBBY_A)
        assert (snap["removed_at"], snap["next_number"], snap["manager_role_ids"]) == (None, 4, [ROLE_1])

    @pytest.mark.parametrize("prefix", ["", "   ", "!!!", "a" * 21])
    def test_prefix_must_be_1_to_20_after_normalizing(self, client, prefix):
        assert fields(client.post(LOBBIES, json=body(name_prefix=prefix))) == {"name_prefix"}
        assert client.guild.lobby.sent == []

    def test_prefix_20_chars_ok(self, client):
        assert client.post(LOBBIES, json=body(name_prefix="a" * 20)).status_code == 200

    def test_validation_errors(self, client):
        r = client.post(
            LOBBIES,
            json=body(
                ticket_category_id=str(LOBBY_A),  # 不是分類
                manager_role_ids=[str(EVERYONE), str(ROLE_MANAGED), "999", str(ROLE_1), str(ROLE_1), "abc"],
                max_open=0,
                button_label="x" * 81,
                button_emoji=EMOJI_GONE,
            ),
        )
        assert fields(r) == {
            "ticket_category_id",
            "manager_role_ids.0",
            "manager_role_ids.1",
            "manager_role_ids.2",
            "manager_role_ids.4",
            "manager_role_ids.5",
            "max_open",
            "button_label",
            "button_emoji",
        }

    def test_valid_custom_emoji_and_blank_label(self, client):
        r = client.post(LOBBIES, json=body(button_emoji=EMOJI_OK, button_label="  "))
        assert r.status_code == 200, r.text
        snap = client.repo.get_ticket_lobby_snapshot(LOBBY_A)
        assert (snap["button_emoji"], snap["button_label"]) == (EMOJI_OK, None)

    def test_empty_message_and_too_long_message_rejected(self, client):
        assert client.post(LOBBIES, json=body(message={"content": None, "embed": None})).status_code == 400
        r = client.post(LOBBIES, json=body(message={"content": "x" * 2001, "embed": None}))
        assert "content" in fields(r)
        assert client.guild.lobby.sent == []

    def test_missing_channel(self, client):
        r = client.post(LOBBIES, json=body(lobby_channel={"kind": "existing", "id": "123"}))
        assert fields(r) == {"lobby_channel"}

    def test_new_channel_name_validation(self, client):
        r = client.post(LOBBIES, json=body(lobby_channel={"kind": "new", "name": "  ", "category_id": "x"}))
        assert fields(r) == {"lobby_channel.name", "lobby_channel.category_id"}

    def test_unavailable_changes_nothing(self, client):
        client.guild.unavailable = True
        r = client.post(LOBBIES, json=body())
        assert (r.status_code, r.json()["error"]) == (503, "guild_unavailable")
        assert client.guild.lobby.sent == []
        assert client.repo.get_ticket_lobby_snapshot(LOBBY_A) is None

    def test_discord_error_is_502(self, client):
        client.guild.lobby.fail_send = True
        r = client.post(LOBBIES, json=body())
        assert (r.status_code, r.json()["error"]) == (502, "discord_error")
        assert client.repo.get_ticket_lobby_snapshot(LOBBY_A) is None

    def test_missing_bot_permission_does_not_block_saving(self, client):
        client.guild.ticket_category.perms["manage_channels"] = False
        assert client.post(LOBBIES, json=body()).status_code == 200


class TestUpdate:
    def put(self, client, original=None, **kw):
        if original is None:
            original = client.get(f"{LOBBIES}/{LOBBY_A}").json()["original"]
        return client.put(f"{LOBBIES}/{LOBBY_A}", json={**body(**kw), "original": original})

    def test_round_trip_without_changes_has_no_false_conflict(self, client):
        add_lobby(client)
        current = client.get(f"{LOBBIES}/{LOBBY_A}").json()
        r = self.put(
            client,
            name_prefix="old",
            message=current["content"],
            button_label=None,
            manager_role_ids=current["manager_role_ids"],
        )
        assert r.status_code == 200, r.text

    def test_update_edits_message_and_saves(self, client):
        old = add_lobby(client)
        r = self.put(client, name_prefix="Support", max_open=3, manager_role_ids=[str(ROLE_1)])
        assert r.status_code == 200, r.text
        snap = client.repo.get_ticket_lobby_snapshot(LOBBY_A)
        assert (snap["name_prefix"], snap["max_open"], snap["message_id"]) == ("support", 3, OLD_MESSAGE)
        assert old.edits[0]["embeds"][0].description == "請按按鈕"

    def test_conflict_returns_latest_and_changes_nothing(self, client):
        old = add_lobby(client)
        original = client.get(f"{LOBBIES}/{LOBBY_A}").json()["original"]
        client.repo.update_ticket_lobby_if(LOBBY_A, {}, {"name_prefix": "someone-else"})
        r = self.put(client, original=original)
        assert r.status_code == 409
        data = r.json()
        assert (data["error"], data["deleted"]) == ("conflict", False)
        assert data["current"]["name_prefix"] == "someone-else"
        assert old.edits == []
        assert client.repo.get_ticket_lobby_snapshot(LOBBY_A)["name_prefix"] == "someone-else"

    def test_manager_roles_change_is_a_conflict(self, client):
        add_lobby(client)
        original = client.get(f"{LOBBIES}/{LOBBY_A}").json()["original"]
        client.repo.set_lobby_manager_roles(LOBBY_A, [ROLE_1, ROLE_2])
        assert self.put(client, original=original).status_code == 409

    def test_removed_lobby_is_deleted_conflict(self, client):
        add_lobby(client)
        original = client.get(f"{LOBBIES}/{LOBBY_A}").json()["original"]
        client.repo.remove_ticket_lobby(LOBBY_A)
        r = self.put(client, original=original)
        assert (r.status_code, r.json()["deleted"]) == (409, True)

    def test_manager_roles_applied_to_existing_tickets(self, client):
        add_lobby(client)
        add_ticket_for(client, T1)
        r = self.put(client, manager_role_ids=[str(ROLE_2)])
        assert r.status_code == 200, r.text
        calls = client.guild.channels[T1].permission_calls
        assert [(c[0], c[1] is None) for c in calls] == [(ROLE_2, False), (ROLE_1, True)]
        assert all("透過後台" in c[2] for c in calls)

    def test_partial_failure_is_listed_and_settings_saved(self, client):
        add_lobby(client)
        add_ticket_for(client, T1)

        async def forbidden(role, *, overwrite, reason=None):
            raise discord.Forbidden(SimpleNamespace(status=403, reason="no"), "missing")

        client.guild.channels[T1].set_permissions = forbidden
        r = self.put(client, manager_role_ids=[str(ROLE_2)])
        assert r.status_code == 200
        assert [f["channel_id"] for f in r.json()["failures"]] == [str(T1)]
        assert client.repo.get_ticket_lobby_snapshot(LOBBY_A)["manager_role_ids"] == [ROLE_2]

    def test_deleted_role_and_gone_emoji_already_set_are_kept(self, client):
        add_lobby(client, button_emoji=EMOJI_GONE)
        client.repo.set_lobby_manager_roles(LOBBY_A, [ROLE_1, 999])
        r = self.put(client, manager_role_ids=[str(ROLE_1), "999"], button_emoji=EMOJI_GONE)
        assert r.status_code == 200, r.text

    def test_reselect_channel_when_lobby_channel_deleted(self, client):
        add_lobby(client)
        add_ticket_for(client, T1)
        del client.guild.channels[LOBBY_A]
        new = Channel(LOBBY_NEW, "新大廳")
        client.guild.channels[LOBBY_NEW] = new
        r = self.put(client, lobby_channel={"kind": "existing", "id": str(LOBBY_NEW)}, original=_original_of(client))
        assert r.status_code == 200, r.text
        assert r.json()["channel_id"] == str(LOBBY_NEW)
        assert len(new.sent) == 1
        assert client.repo.get_ticket_lobby_snapshot(LOBBY_A) is None
        assert client.repo.get_ticket_channel(T1).lobby_channel_id == LOBBY_NEW

    def test_cannot_change_channel_while_old_one_exists(self, client):
        add_lobby(client)
        client.guild.channels[LOBBY_NEW] = Channel(LOBBY_NEW, "新大廳")
        r = self.put(client, lobby_channel={"kind": "existing", "id": str(LOBBY_NEW)})
        assert fields(r) == {"lobby_channel"}

    def test_unavailable_does_not_resend_or_write(self, client):
        add_lobby(client)
        original = client.get(f"{LOBBIES}/{LOBBY_A}").json()["original"]
        client.guild.unavailable = True
        client.guild.channels.clear()  # 快取是空的
        r = self.put(client, original=original)
        assert (r.status_code, r.json()["error"]) == (503, "guild_unavailable")
        assert client.repo.get_ticket_lobby_snapshot(LOBBY_A)["name_prefix"] == "old"

    def test_validation_error_before_discord(self, client):
        old = add_lobby(client)
        assert fields(self.put(client, name_prefix="!!!")) == {"name_prefix"}
        assert old.edits == []


class TestDelete:
    def delete(self, client, original=None):
        if original is None:
            original = client.get(f"{LOBBIES}/{LOBBY_A}").json()["original"]
        return client.request("DELETE", f"{LOBBIES}/{LOBBY_A}", json={"original": original})

    def test_removes_button_keeps_message_and_channel(self, client):
        old = add_lobby(client)
        add_ticket_for(client, T1)
        r = self.delete(client)
        assert (r.status_code, r.json()) == (200, {"removed": True, "button_removed": True})
        assert old.edits == [{"view": None}]
        assert not old.deleted and not client.guild.lobby.deleted
        assert client.get(URL).json()["lobbies"] == []
        assert [t["channel"]["id"] for t in client.get(URL).json()["unassigned"]] == [str(T1)]
        assert client.repo.get_ticket_channel(T1).lobby_channel_id is None

    def test_conflict(self, client):
        old = add_lobby(client)
        original = client.get(f"{LOBBIES}/{LOBBY_A}").json()["original"]
        client.repo.update_ticket_lobby_if(LOBBY_A, {}, {"max_open": 9})
        r = self.delete(client, original)
        assert (r.status_code, r.json()["deleted"]) == (409, False)
        assert old.edits == []
        assert client.repo.get_ticket_lobby_snapshot(LOBBY_A)["removed_at"] is None

    def test_already_removed_is_deleted_conflict(self, client):
        add_lobby(client)
        original = client.get(f"{LOBBIES}/{LOBBY_A}").json()["original"]
        client.repo.remove_ticket_lobby(LOBBY_A)
        r = self.delete(client, original)
        assert (r.status_code, r.json()["deleted"]) == (409, True)

    def test_unavailable_keeps_button_and_record(self, client):
        old = add_lobby(client)
        original = client.get(f"{LOBBIES}/{LOBBY_A}").json()["original"]
        client.guild.unavailable = True
        client.guild.channels.clear()
        r = self.delete(client, original)
        assert (r.status_code, r.json()["error"]) == (503, "guild_unavailable")
        assert old.edits == []
        assert client.repo.get_ticket_lobby_snapshot(LOBBY_A)["removed_at"] is None

    def test_discord_error_keeps_record(self, client):
        old = add_lobby(client)
        old.fail_edit = True
        r = self.delete(client)
        assert (r.status_code, r.json()["error"]) == (502, "discord_error")
        assert client.repo.get_ticket_lobby_snapshot(LOBBY_A)["removed_at"] is None


def add_ticket_for(client, cid, **kw):
    add_ticket(SimpleNamespace(guild=client.guild, repo=client.repo), cid, **kw)
    client.guild.channels[cid] = Channel(cid, f"ticket-{cid}")


def _original_of(client) -> dict:
    snap = client.repo.get_ticket_lobby_snapshot(LOBBY_A)
    role_ids = [str(r) for r in snap["manager_role_ids"]]
    return {
        "ticket_category_id": str(snap["ticket_category_id"]),
        "name_prefix": snap["name_prefix"],
        "one_per_user": snap["one_per_user"],
        "max_open": snap["max_open"],
        "content_json": snap["content_json"],
        "button_label": snap["button_label"],
        "button_emoji": snap["button_emoji"],
        "manager_role_ids": role_ids,
    }


class TestReviewFixes:
    def test_update_with_unreadable_lobby_channel_explains_missing_permission(self, client):
        add_lobby(client)
        original = client.get(f"{LOBBIES}/{LOBBY_A}").json()["original"]

        async def forbidden(mid):
            raise discord.Forbidden(SimpleNamespace(status=403, reason="no"), "missing")

        client.guild.lobby.fetch_message = forbidden
        r = client.put(f"{LOBBIES}/{LOBBY_A}", json={**body(), "original": original})
        assert (r.status_code, r.json()["error"]) == (400, "bot_missing_permission")
        assert "Read Message History" in r.json()["fields"][0]["reason"]
        assert client.guild.lobby.sent == []

    def test_remove_without_access_still_removes_and_says_button_is_left(self, client):
        old = add_lobby(client)
        original = client.get(f"{LOBBIES}/{LOBBY_A}").json()["original"]

        async def forbidden(**kwargs):
            raise discord.Forbidden(SimpleNamespace(status=403, reason="no"), "missing")

        old.edit = forbidden
        r = client.request("DELETE", f"{LOBBIES}/{LOBBY_A}", json={"original": original})
        assert (r.status_code, r.json()) == (200, {"removed": True, "button_removed": False})
        assert client.repo.get_ticket_lobby_snapshot(LOBBY_A)["removed_at"] is not None
