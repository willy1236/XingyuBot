"""伺服器管理後台 S-01：區塊權限對照、require_section 與 GET /dashboard/guilds/{id}/sections（假 Discord，真實 PostgreSQL）。"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from test_dashboard_auth import dashboard_env, make_app, make_session  # noqa: F401  (fixture 與 helper)
from test_dashboard_guilds import (
    ADMIN,
    BAN,
    KICK,
    MANAGE_CHANNELS,
    MANAGE_GUILD,
    MANAGE_MESSAGES,
    MANAGE_ROLES,
    MODERATE,
    g,
    seed_token,
)
from test_dashboard_guilds import discord as discord_env  # noqa: F401  (fixture)
from test_identity import repo  # noqa: F401

from starlib import sclient
from starServer.dashboard import guilds
from starServer.dashboard.access import SECTION_RULES, Section, require_guild_access, require_section

GUILD_ID = 1001


def fake_bot(in_guild: bool = True, ready: bool = True):
    pool = ThreadPoolExecutor(max_workers=1)
    return SimpleNamespace(
        is_ready=lambda: ready,
        get_guild=lambda gid: SimpleNamespace(id=gid) if in_guild and gid == GUILD_ID else None,
        submit=lambda coro: pool.submit(asyncio.run, coro),
    )


@pytest.fixture
def client(discord_env, repo, dashboard_env, monkeypatch) -> TestClient:  # noqa: F811
    seed_token(repo, dashboard_env.credential_id)
    make_session(repo)
    monkeypatch.setattr(sclient, "bot", fake_bot())
    app = make_app()
    for probe, dep in {
        "notify": require_section(Section.NOTIFY),
        "ban": require_section(Section.WARNINGS, "ban"),
        "remove": require_section(Section.WARNINGS, "remove"),
        "legacy": require_guild_access,
    }.items():
        app.get(f"/dashboard/guilds/{{guild_id}}/probe-{probe}")(lambda guild_id=Depends(dep): {"guild_id": guild_id})
    c = TestClient(app, base_url="https://testserver", follow_redirects=False)
    c.cookies.set("dashboard_session", "sid")
    return c


def sections(client, discord_env, permissions: int, owner: bool = False):  # noqa: F811
    guilds._cache.clear()
    discord_env.guilds = [g(str(GUILD_ID), "guild", permissions, owner=owner)]
    res = client.get(f"/dashboard/guilds/{GUILD_ID}/sections")
    return res.status_code, res.json()


class TestSectionsEndpoint:
    def test_ban_only(self, client, discord_env):  # noqa: F811
        status, body = sections(client, discord_env, BAN)
        assert status == 200
        assert body == {"sections": [{"key": "warnings", "actions": ["view", "remove", "ban"]}]}

    def test_manage_roles_only(self, client, discord_env):  # noqa: F811
        _, body = sections(client, discord_env, MANAGE_ROLES)
        assert body == {
            "sections": [
                {"key": "reaction_roles", "actions": ["view"]},
                {"key": "warnings", "actions": ["view"]},
            ]
        }

    def test_manage_channels(self, client, discord_env):  # noqa: F811
        _, body = sections(client, discord_env, MANAGE_CHANNELS)
        assert [s["key"] for s in body["sections"]] == ["notify", "dynamic_voice", "tickets", "warnings"]

    def test_manage_guild_only(self, client, discord_env):  # noqa: F811
        _, body = sections(client, discord_env, MANAGE_GUILD)
        assert [s["key"] for s in body["sections"]] == ["warnings", "settings"]

    def test_manage_messages_only(self, client, discord_env):  # noqa: F811
        _, body = sections(client, discord_env, MANAGE_MESSAGES)
        assert body["sections"] == [
            {"key": "warnings", "actions": ["view", "add", "remove"]},
            {"key": "giveaways", "actions": ["view", "end", "redraw"]},
        ]

    def test_moderate_and_kick(self, client, discord_env):  # noqa: F811
        _, body = sections(client, discord_env, MODERATE | KICK)
        assert body == {"sections": [{"key": "warnings", "actions": ["view", "remove", "timeout", "kick"]}]}

    @pytest.mark.parametrize(("permissions", "owner"), [(ADMIN, False), (0, True)])
    def test_full_access_gets_everything(self, client, discord_env, permissions, owner):  # noqa: F811
        _, body = sections(client, discord_env, permissions, owner)
        assert [s["key"] for s in body["sections"]] == [s.value for s in Section]
        warnings = next(s for s in body["sections"] if s["key"] == "warnings")
        assert warnings["actions"] == list(SECTION_RULES[Section.WARNINGS])

    def test_no_entry_permission(self, client, discord_env):  # noqa: F811
        status, body = sections(client, discord_env, 0x400)  # 只有 View Channel
        assert (status, body) == (403, {"error": "no_permission"})

    def test_user_not_in_guild(self, client, discord_env):  # noqa: F811
        discord_env.guilds = []
        res = client.get(f"/dashboard/guilds/{GUILD_ID}/sections")
        assert (res.status_code, res.json()) == (403, {"error": "no_permission"})

    def test_bot_not_in_guild(self, client, discord_env, monkeypatch):  # noqa: F811
        monkeypatch.setattr(sclient, "bot", fake_bot(in_guild=False))
        status, body = sections(client, discord_env, BAN)
        assert (status, body) == (404, {"error": "bot_not_in_guild"})

    @pytest.mark.parametrize("bot", [None, fake_bot(ready=False)])
    def test_bot_unavailable(self, client, discord_env, monkeypatch, bot):  # noqa: F811
        monkeypatch.setattr(sclient, "bot", bot)
        status, body = sections(client, discord_env, BAN)
        assert (status, body) == (503, {"error": "bot_unavailable"})

    def test_requires_session(self, client):
        client.cookies.clear()
        assert client.get(f"/dashboard/guilds/{GUILD_ID}/sections").json() == {"error": "session_expired"}


class TestRequireSection:
    def get(self, client, probe):
        return client.get(f"/dashboard/guilds/{GUILD_ID}/probe-{probe}")

    def set_perms(self, discord_env, permissions):  # noqa: F811
        guilds._cache.clear()
        discord_env.guilds = [g(str(GUILD_ID), "guild", permissions)]

    def test_action_needs_its_own_permission(self, client, discord_env):  # noqa: F811
        self.set_perms(discord_env, KICK)
        assert self.get(client, "ban").json() == {"error": "no_permission"}
        assert self.get(client, "remove").json() == {"guild_id": GUILD_ID}
        self.set_perms(discord_env, BAN)
        assert self.get(client, "ban").json() == {"guild_id": GUILD_ID}

    @pytest.mark.parametrize("bit", [KICK, BAN, MANAGE_MESSAGES])
    def test_remove_accepts_any_of_three(self, client, discord_env, bit):  # noqa: F811
        self.set_perms(discord_env, bit)
        assert self.get(client, "remove").status_code == 200

    def test_remove_rejects_others(self, client, discord_env):  # noqa: F811
        self.set_perms(discord_env, MODERATE | MANAGE_ROLES | MANAGE_GUILD)
        assert self.get(client, "remove").status_code == 403

    @pytest.mark.parametrize("probe", ["notify", "legacy"])
    def test_notify_and_legacy_alias_need_manage_channels(self, client, discord_env, probe):  # noqa: F811
        self.set_perms(discord_env, BAN | MANAGE_MESSAGES | MANAGE_GUILD)
        res = self.get(client, probe)
        assert (res.status_code, res.json()) == (403, {"error": "no_permission"})
        self.set_perms(discord_env, MANAGE_CHANNELS)
        assert self.get(client, probe).json() == {"guild_id": GUILD_ID}

    def test_bot_not_in_guild(self, client, discord_env, monkeypatch):  # noqa: F811
        self.set_perms(discord_env, MANAGE_CHANNELS)
        monkeypatch.setattr(sclient, "bot", fake_bot(in_guild=False))
        res = self.get(client, "notify")
        assert (res.status_code, res.json()) == (404, {"error": "bot_not_in_guild"})

    def test_unknown_action_fails_at_definition(self):
        with pytest.raises(KeyError):
            require_section(Section.NOTIFY, "ban")
