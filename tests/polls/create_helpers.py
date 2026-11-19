"""後台建立投票測試共用：假伺服器、`client` fixture 與 `post()`。"""

from __future__ import annotations

from types import SimpleNamespace

import discord
import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from starDiscord.uiElement import view as view_module
from starlib import sclient
from starlib.database import Poll
from tests.helpers.dashboard_auth import USER_ID, make_app, make_session
from tests.helpers.dashboard_guilds import MANAGE_MESSAGES, g
from tests.helpers.dashboard_notifies import GUILD_ID
from tests.polls.dashboard_helpers import FakeBot

URL = f"/dashboard/guilds/{GUILD_ID}/polls"
OPERATOR = int(USER_ID)
HEADERS = {"Origin": "https://domalyze.net"}
OK = discord.Permissions(view_channel=True, send_messages=True)
MUTE = discord.Permissions(view_channel=True)


class FakeChannel:
    def __init__(self, cid: int, name: str, bot_perms=OK, operator_perms=OK, type=discord.ChannelType.text, position=0):
        self.id = cid
        self.name = name
        self.type = type
        self.position = position
        self.category = None
        self.bot_perms = bot_perms
        self.operator_perms = operator_perms
        self.sent: list[dict] = []
        self.send_error: Exception | None = None

    def permissions_for(self, member):
        return self.bot_perms if member.is_bot else self.operator_perms

    async def send(self, **kwargs):
        if self.send_error is not None:
            raise self.send_error
        self.sent.append(kwargs)
        return SimpleNamespace(id=9000 + len(self.sent))


def make_role(rid: int, name: str, position: int, *, default=False, managed=False):
    return SimpleNamespace(
        id=rid,
        name=name,
        position=position,
        managed=managed,
        color=SimpleNamespace(value=0xFF0000),
        is_default=lambda: default,
        mention=f"<@&{rid}>",
    )


class FakeGuild:
    def __init__(self):
        self.id = GUILD_ID
        self.unavailable = False
        self.me = SimpleNamespace(is_bot=True, display_name="bot")
        self.operator = SimpleNamespace(
            is_bot=False,
            id=OPERATOR,
            name="管理員",
            display_name="管理員",
            display_avatar=SimpleNamespace(url="https://cdn.example/a.png"),
        )
        self.channels = {
            500: FakeChannel(500, "一般", position=1),
            501: FakeChannel(501, "公告", type=discord.ChannelType.news, position=2),
            502: FakeChannel(502, "bot 不能發言", bot_perms=MUTE, position=3),
            503: FakeChannel(503, "你不能發言", operator_perms=MUTE, position=4),
            504: FakeChannel(504, "語音", type=discord.ChannelType.voice, position=5),
        }
        self.roles = [
            make_role(GUILD_ID, "@everyone", 0, default=True),
            make_role(600, "成員", 2),
            make_role(601, "整合", 3, managed=True),
            make_role(602, "VIP", 5),
        ]
        self.in_guild = True

    @property
    def text_channels(self):
        return [c for c in self.channels.values() if c.type in (discord.ChannelType.text, discord.ChannelType.news)]

    def get_member(self, uid: int):
        return self.operator if self.in_guild and uid == OPERATOR else None

    def get_role(self, rid: int):
        return next((r for r in self.roles if r.id == rid), None)

    def get_channel(self, cid: int):
        return self.channels.get(cid)


@pytest.fixture
def client(discord_env, repo, dashboard_env, monkeypatch) -> TestClient:
    make_session(repo)
    discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_MESSAGES)]
    monkeypatch.setattr(view_module, "sqldb", repo)
    guild = FakeGuild()
    monkeypatch.setattr(sclient, "bot", FakeBot(guild))
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
    c.cookies.set("dashboard_session", "sid")
    c.guild = guild  # pyright: ignore[reportAttributeAccessIssue]
    c.repo = repo  # pyright: ignore[reportAttributeAccessIssue]
    c.discord_env = discord_env  # pyright: ignore[reportAttributeAccessIssue]
    c.before = poll_count(c)  # pyright: ignore[reportAttributeAccessIssue]
    return c


def post(client, **overrides):
    data = {"channel_id": "500", "title": "午餐吃什麼", "options": ["拉麵", "咖哩"]}
    data.update(overrides)
    return client.post(URL, json=data, headers=HEADERS)


def poll_count(client) -> int:
    client.repo.session.expire_all()
    return len(client.repo.session.exec(select(Poll)).all())
