"""後台動態語音測試共用：假語音伺服器與 `client` fixture。"""

from __future__ import annotations

from types import SimpleNamespace

import discord
import pytest
from fastapi.testclient import TestClient

from starlib import sclient
from starServer.dashboard import dynamic_voice
from tests.helpers.dashboard_auth import make_app, make_session
from tests.helpers.dashboard_guilds import MANAGE_CHANNELS, g
from tests.helpers.dashboard_notifies import GUILD_ID, fake_bot

LOBBY = 31
OTHER_LOBBY = 32
TEXT_CHANNEL = 33
STAGE_CHANNEL = 34
NO_CATEGORY_LOBBY = 35


def perms(**missing: bool) -> SimpleNamespace:
    values = dict(manage_channels=True, manage_roles=True, move_members=True, send_messages=True, view_channel=True)
    values.update({k: False for k in missing})
    return SimpleNamespace(**values)


def vchannel(cid, name, *, type=discord.ChannelType.voice, category="遊戲", missing=(), position=0):
    p = perms(**dict.fromkeys(missing, True))
    cat = SimpleNamespace(name=category, permissions_for=lambda _me: perms()) if category else None
    return SimpleNamespace(id=cid, name=name, type=type, category=cat, position=position, permissions_for=lambda _me: p)


def fake_voice_guild(*, guild_missing=(), **channel_missing) -> SimpleNamespace:
    chans = [
        vchannel(LOBBY, "大廳", missing=channel_missing.get("lobby", ())),
        vchannel(OTHER_LOBBY, "另一個大廳", position=1),
        vchannel(TEXT_CHANNEL, "文字", type=discord.ChannelType.text),
        vchannel(STAGE_CHANNEL, "舞台", type=discord.ChannelType.stage_voice),
        vchannel(NO_CATEGORY_LOBBY, "最上層", category=None, position=2),
    ]
    by_id = {c.id: c for c in chans}
    me = SimpleNamespace(guild_permissions=perms(**dict.fromkeys(guild_missing, True)))
    guild = SimpleNamespace(
        id=GUILD_ID,
        me=me,
        get_channel=by_id.get,
        voice_channels=[c for c in chans if c.type == discord.ChannelType.voice],
        get_member=lambda _uid: SimpleNamespace(name="willy"),
    )
    for c in chans:
        c.guild = guild
    return guild


@pytest.fixture
def client(discord_env, repo, dashboard_env, monkeypatch) -> TestClient:
    make_session(repo)
    discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_CHANNELS)]
    monkeypatch.setattr(dynamic_voice, "sqldb", repo)
    monkeypatch.setattr(sclient, "bot", fake_bot(fake_voice_guild()))
    repo.cache.dynamic_voice_lobby.load({})
    repo.cache.dynamic_voice_room.load([])
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
    c.cookies.set("dashboard_session", "sid")
    c.repo = repo  # pyright: ignore[reportAttributeAccessIssue]
    c.discord_env = discord_env  # pyright: ignore[reportAttributeAccessIssue]
    return c


def use_guild(monkeypatch, guild):
    monkeypatch.setattr(sclient, "bot", fake_bot(guild))


URL = f"/dashboard/guilds/{GUILD_ID}/dynamic-voice"
