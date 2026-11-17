"""伺服器管理後台：伺服器清單與權限判斷（假 bot，真實 PostgreSQL）。

其他 test_dashboard_*.py 共用這裡的 `discord` fixture 與 `g()`：`discord.guilds` 是 bot 成員快取裡這位使用者的資料，
各檔自己的假 bot 只要提供 get_guild，權限由正式的 `_member_perms` 依這份資料判斷。
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import discord as dpy
import pytest
from fastapi.testclient import TestClient
from test_dashboard_auth import (  # noqa: F401  (fixture 與 helper)
    USER_ID,
    dashboard_env,
    make_app,
    make_session,
)
from test_identity import repo  # noqa: F401

from starlib import sclient
from starServer.dashboard import guilds
from starServer.dashboard.errors import DashboardError

ADMIN = 0x8
MANAGE_CHANNELS = 0x10
MANAGE_GUILD = 0x20
KICK = 0x2
BAN = 0x4
MANAGE_MESSAGES = 0x2000
MANAGE_ROLES = 0x10000000
MODERATE = 0x10000000000


def g(gid: str, name: str, permissions: int = 0, owner: bool = False) -> dict:
    """使用者在伺服器 gid 的成員資料：permissions 是 guild_permissions 的 bits，owner 表示是伺服器擁有者。"""
    return {"id": gid, "name": name, "owner": owner, "permissions": permissions}


class FakeDiscord:
    def __init__(self):
        # 使用者是成員的伺服器；不在這裡的伺服器視為不是成員
        self.guilds: list[dict] = []


@pytest.fixture
def discord(monkeypatch, dashboard_env, repo) -> FakeDiscord:  # noqa: F811
    fake = FakeDiscord()
    real_member_perms = guilds._member_perms

    def member_perms(guild, user_id: int) -> guilds.GuildPerms:
        """把各檔自己的假伺服器換成帶有 fake.guilds 成員資料的伺服器，再交給正式的判斷。"""
        entry = next((e for e in fake.guilds if e["id"] == str(guild.id)), None)
        members = [member(user_id, entry["permissions"])] if entry else []
        owner_id = user_id if entry and entry["owner"] else 1
        return real_member_perms(bot_guild(guild.id, "guild", members, owner_id=owner_id), user_id)

    monkeypatch.setattr(guilds, "_member_perms", member_perms)
    return fake


# ====== 假 bot（成員快取） ======
def member(user_id: str | int, permissions: int = 0):
    return SimpleNamespace(id=int(user_id), guild_permissions=dpy.Permissions(permissions))


def bot_guild(gid: int, name: str, members=(), owner_id: int = 1, icon: str | None = None):
    by_id = {m.id: m for m in members}
    return SimpleNamespace(
        id=gid,
        name=name,
        owner_id=owner_id,
        icon=SimpleNamespace(url=icon) if icon else None,
        get_member=by_id.get,
    )


def fake_bot(guild_list=(), ready: bool = True):
    pool = ThreadPoolExecutor(max_workers=1)
    by_id = {x.id: x for x in guild_list}
    return SimpleNamespace(
        is_ready=lambda: ready,
        guilds=list(guild_list),
        get_guild=by_id.get,
        submit=lambda coro: pool.submit(asyncio.run, coro),
    )


# ====== GET /dashboard/guilds ======
class TestListEndpoint:
    @pytest.fixture
    def client(self, repo, dashboard_env) -> TestClient:  # noqa: F811
        make_session(repo)
        c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
        c.cookies.set("dashboard_session", "sid")
        return c

    def test_only_bot_guilds_user_can_enter_sorted(self, client, monkeypatch):
        icon = "https://cdn.discordapp.com/icons/8/a_abc.gif"
        bot_guilds = [
            bot_guild(1, "banana", [member(USER_ID, MANAGE_CHANNELS)]),
            bot_guild(2, "Apple", [member(USER_ID, ADMIN)]),
            bot_guild(3, "cherry", [member(USER_ID, MANAGE_GUILD)]),
            bot_guild(8, "hotel", [member(USER_ID)], owner_id=int(USER_ID), icon=icon),  # 擁有者
            bot_guild(9, "india", [member(USER_ID, BAN)]),
            bot_guild(10, "juliet", [member(USER_ID, MANAGE_ROLES)]),
            bot_guild(11, "kilo", [member(USER_ID, 0x400)]),  # 只有 View Channel → 不出現
            bot_guild(12, "lima", [member("42", ADMIN)]),  # 不是成員 → 不出現
        ]
        monkeypatch.setattr(sclient, "bot", fake_bot(bot_guilds))
        res = client.get("/dashboard/guilds")
        assert res.status_code == 200
        body = res.json()
        assert list(body) == ["guilds"]
        assert [x["name"] for x in body["guilds"]] == ["Apple", "banana", "cherry", "hotel", "india", "juliet"]
        assert body["guilds"][3] == {"id": "8", "name": "hotel", "icon_url": icon}
        assert body["guilds"][0]["icon_url"] is None

    def test_empty(self, client, monkeypatch):
        monkeypatch.setattr(sclient, "bot", fake_bot([]))
        assert client.get("/dashboard/guilds").json() == {"guilds": []}

    def test_reflects_bot_state_every_request(self, client, monkeypatch):
        """權限被拔掉或 bot 被踢出，下一次請求就反映，不經過快取。"""
        guild = bot_guild(1, "a", [member(USER_ID, MANAGE_CHANNELS)])
        monkeypatch.setattr(sclient, "bot", fake_bot([guild]))
        assert [x["id"] for x in client.get("/dashboard/guilds").json()["guilds"]] == ["1"]
        guild.get_member = {int(USER_ID): member(USER_ID)}.get
        assert client.get("/dashboard/guilds").json() == {"guilds": []}
        guild.get_member = {int(USER_ID): member(USER_ID, MANAGE_CHANNELS)}.get
        monkeypatch.setattr(sclient, "bot", fake_bot([]))
        assert client.get("/dashboard/guilds").json() == {"guilds": []}

    def test_bot_not_ready(self, client, monkeypatch):
        monkeypatch.setattr(sclient, "bot", None)
        res = client.get("/dashboard/guilds")
        assert (res.status_code, res.json()) == (503, {"error": "bot_unavailable"})
        monkeypatch.setattr(sclient, "bot", fake_bot([], ready=False))
        assert client.get("/dashboard/guilds").json() == {"error": "bot_unavailable"}

    def test_requires_session(self):
        c = TestClient(make_app(), base_url="https://testserver")
        assert c.get("/dashboard/guilds").json() == {"error": "session_expired"}


# ====== guild_perms ======
class TestGuildPerms:
    def perms(self, monkeypatch, guild, gid: str | int = 1):
        monkeypatch.setattr(sclient, "bot", fake_bot([guild]))
        return asyncio.run(guilds.guild_perms(USER_ID, gid))

    def test_member(self, monkeypatch):
        p = self.perms(monkeypatch, bot_guild(1, "a", [member(USER_ID, MANAGE_CHANNELS | BAN)]))
        assert (p.bits, p.full) == (MANAGE_CHANNELS | BAN, False)
        assert p.manage_channels and not p.manage_guild

    def test_not_member(self, monkeypatch):
        assert self.perms(monkeypatch, bot_guild(1, "a", [member("42", ADMIN)])) == guilds.GuildPerms()

    def test_owner(self, monkeypatch):
        p = self.perms(monkeypatch, bot_guild(1, "a", [member(USER_ID)], owner_id=int(USER_ID)))
        assert p.full and p.manage_guild

    def test_owner_not_yet_in_member_cache(self, monkeypatch):
        assert self.perms(monkeypatch, bot_guild(1, "a", [], owner_id=int(USER_ID))).full

    def test_administrator(self, monkeypatch):
        p = self.perms(monkeypatch, bot_guild(1, "a", [member(USER_ID, ADMIN)]))
        assert p.full and p.manage_channels

    def test_accepts_str_guild_id(self, monkeypatch):
        assert self.perms(monkeypatch, bot_guild(1, "a", [member(USER_ID, BAN)]), gid="1").bits == BAN

    def test_bot_not_in_guild(self, monkeypatch):
        with pytest.raises(DashboardError) as e:
            self.perms(monkeypatch, bot_guild(1, "a", [member(USER_ID, ADMIN)]), gid=999)
        assert (e.value.status, e.value.code) == (404, "bot_not_in_guild")

    @pytest.mark.parametrize("bot", [None, fake_bot([], ready=False)])
    def test_bot_unavailable(self, monkeypatch, bot):
        monkeypatch.setattr(sclient, "bot", bot)
        with pytest.raises(DashboardError) as e:
            asyncio.run(guilds.guild_perms(USER_ID, 1))
        assert (e.value.status, e.value.code) == (503, "bot_unavailable")


class TestPermissionBits:
    def test_permission_bits_match_discord_docs(self):
        assert guilds.KICK_MEMBERS == 1 << 1
        assert guilds.BAN_MEMBERS == 1 << 2
        assert guilds.MANAGE_MESSAGES == 1 << 13
        assert guilds.MANAGE_ROLES == 1 << 28
        assert guilds.MODERATE_MEMBERS == 1 << 40

    @pytest.mark.parametrize("bit", [MANAGE_CHANNELS, MANAGE_ROLES, MANAGE_GUILD, MANAGE_MESSAGES, KICK, BAN, MODERATE])
    def test_can_enter_with_any_entry_bit(self, bit):
        assert guilds.can_enter(guilds.GuildPerms(bit))

    def test_can_enter_rejects_unrelated_bits(self):
        assert not guilds.can_enter(guilds.GuildPerms(0))
        assert not guilds.can_enter(guilds.GuildPerms(0x400 | 0x800))  # View Channel、Send Messages

    def test_can_enter_full_access(self):
        assert guilds.can_enter(guilds.GuildPerms(0, True))
