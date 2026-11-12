"""伺服器管理後台 P-04：鎖定、重開、刪除私人頻道的端點（假 Discord，真實 PostgreSQL）。"""

from __future__ import annotations

import discord
import pytest
from fastapi.testclient import TestClient
from test_dashboard_auth import FRONTEND, USER_ID, dashboard_env, make_app, make_session  # noqa: F401  (fixture 與 helper)
from test_dashboard_guilds import MANAGE_CHANNELS, MANAGE_ROLES, g, seed_token
from test_dashboard_guilds import discord as discord_env  # noqa: F401  (fixture)
from test_dashboard_notifies import GUILD_ID
from test_identity import repo  # noqa: F401
from test_ticket_actions import (
    CONTROL,
    CREATED,
    CREATOR,
    LOBBY,
    ROLE_MANAGER,
    TICKET,
    FakeGuild,
    FakeMember,
    FakeTicketChannel,
    custom_ids,
    http_error,
    ticket_overwrites,
)
from test_ticket_lobby import FakeBot

from starDiscord import ticket_channel, ticket_lobby
from starlib import sclient
from starlib.database import TicketChannel, TicketChannelLobby
from starServer.dashboard import tickets

CHANNELS = f"/dashboard/guilds/{GUILD_ID}/tickets/channels"
ACTOR_ID = int(USER_ID)


class Guild(FakeGuild):
    def __init__(self):
        super().__init__()
        self.id = GUILD_ID
        self.members[ACTOR_ID] = FakeMember(ACTOR_ID, manage_channels=True)


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
    for module in (tickets, ticket_lobby, ticket_channel):
        monkeypatch.setattr(module, "sqldb", repo)
    monkeypatch.setattr(ticket_channel, "_locks", {})
    monkeypatch.setattr(ticket_lobby, "_locks", {})
    guild = Guild()
    bot = WebBot(guild)
    monkeypatch.setattr(sclient, "bot", bot)
    repo.merge(TicketChannelLobby(channel_id=LOBBY, category_id=1, guild_id=GUILD_ID, message_id=1, ticket_category_id=1))
    repo.set_lobby_manager_roles(LOBBY, [ROLE_MANAGER])
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False, headers={"Origin": FRONTEND})
    c.cookies.set("dashboard_session", "sid")
    c.repo = repo  # pyright: ignore[reportAttributeAccessIssue]
    c.guild = guild  # pyright: ignore[reportAttributeAccessIssue]
    c.discord_env = discord_env  # pyright: ignore[reportAttributeAccessIssue]
    return c


def add_ticket(client, *, closed=False, guild_id=GUILD_ID) -> FakeTicketChannel:
    client.repo.merge(
        TicketChannel(
            channel_id=TICKET,
            guild_id=guild_id,
            creator_id=CREATOR,
            created_at=CREATED,
            closed_at=CREATED if closed else None,
            closer_id=ACTOR_ID if closed else None,
            view_message_id=CONTROL,
            lobby_channel_id=LOBBY,
            locked_overwrites_json="{}" if closed else None,
        )
    )
    channel = FakeTicketChannel(client.guild, TICKET, ticket_overwrites())
    client.guild.channels[TICKET] = channel
    return channel


def snap(client):
    return client.repo.get_ticket_snapshot(TICKET)


class TestAccess:
    def test_manage_roles_only_is_forbidden(self, client):
        add_ticket(client)
        client.discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_ROLES)]
        assert client.post(f"{CHANNELS}/{TICKET}/lock").status_code == 403
        assert client.post(f"{CHANNELS}/{TICKET}/reopen").status_code == 403
        assert client.delete(f"{CHANNELS}/{TICKET}").status_code == 403
        assert snap(client)["closed_at"] is None

    def test_no_session(self, client):
        client.cookies.clear()
        assert client.post(f"{CHANNELS}/{TICKET}/lock").status_code == 401

    @pytest.mark.parametrize(("method", "path"), [("POST", "/lock"), ("POST", "/reopen"), ("DELETE", "")])
    def test_unavailable_changes_nothing(self, client, method, path):
        channel = add_ticket(client)
        client.guild.unavailable = True
        r = client.request(method, f"{CHANNELS}/{TICKET}{path}")
        assert (r.status_code, r.json()["error"]) == (503, "guild_unavailable")
        assert channel.edits == [] and snap(client) is not None


class TestLock:
    def test_lock(self, client):
        channel = add_ticket(client)
        r = client.post(f"{CHANNELS}/{TICKET}/lock")
        assert r.status_code == 200, r.text
        assert r.json() == {"channel_id": str(TICKET), "status": "locked", "changed": True}
        s = snap(client)
        assert s["closed_at"] is not None and s["closer_id"] == ACTOR_ID
        assert channel.send_of(f"member:{CREATOR}") is False
        assert "透過後台" in channel.edits[0][1]
        assert custom_ids(channel.messages[CONTROL].edits[0]["view"])[0].startswith("ticket_reopen_")

    def test_already_locked(self, client):
        add_ticket(client, closed=True)
        assert client.post(f"{CHANNELS}/{TICKET}/lock").json()["changed"] is False

    def test_not_found(self, client):
        assert client.post(f"{CHANNELS}/{TICKET}/lock").status_code == 404

    def test_other_guild_ticket_is_not_found(self, client):
        add_ticket(client, guild_id=GUILD_ID + 1)
        assert client.post(f"{CHANNELS}/{TICKET}/lock").status_code == 404

    def test_channel_deleted_in_discord(self, client):
        add_ticket(client)
        client.guild.channels.pop(TICKET)
        r = client.post(f"{CHANNELS}/{TICKET}/lock")
        assert (r.status_code, r.json()["error"]) == (404, "not_found")
        assert snap(client) is None

    def test_bot_missing_permission(self, client):
        channel = add_ticket(client)
        channel.fail_edit = http_error(discord.Forbidden, 403)
        r = client.post(f"{CHANNELS}/{TICKET}/lock")
        assert (r.status_code, r.json()["error"]) == (400, "bot_missing_permission")

    def test_discord_error(self, client):
        channel = add_ticket(client)
        channel.fail_edit = http_error()
        r = client.post(f"{CHANNELS}/{TICKET}/lock")
        assert (r.status_code, r.json()["error"]) == (502, "discord_error")

    def test_actor_not_in_guild(self, client):
        add_ticket(client)
        client.guild.members.pop(ACTOR_ID)
        assert client.post(f"{CHANNELS}/{TICKET}/lock").status_code == 403


class TestReopen:
    def test_reopen_after_lock_restores(self, client):
        channel = add_ticket(client)
        before = channel.state()
        client.post(f"{CHANNELS}/{TICKET}/lock")
        r = client.post(f"{CHANNELS}/{TICKET}/reopen")
        assert r.json() == {"channel_id": str(TICKET), "status": "open", "changed": True}
        assert channel.state() == before
        assert snap(client)["closed_at"] is None

    def test_already_open(self, client):
        add_ticket(client)
        assert client.post(f"{CHANNELS}/{TICKET}/reopen").json()["changed"] is False


class TestDelete:
    def test_delete_removes_channel_and_record(self, client):
        add_ticket(client, closed=True)
        r = client.delete(f"{CHANNELS}/{TICKET}")
        assert r.json() == {"channel_id": str(TICKET), "status": "deleted", "changed": True}
        assert TICKET not in client.guild.channels and snap(client) is None

    def test_already_deleted_is_success(self, client):
        r = client.delete(f"{CHANNELS}/{TICKET}")
        assert r.status_code == 200 and r.json()["changed"] is False

    def test_bot_missing_permission(self, client):
        channel = add_ticket(client)
        channel.fail_delete = http_error(discord.Forbidden, 403)
        r = client.delete(f"{CHANNELS}/{TICKET}")
        assert (r.status_code, r.json()["error"]) == (400, "bot_missing_permission")
        assert snap(client) is not None
