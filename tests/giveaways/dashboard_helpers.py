"""後台抽獎測試共用：假伺服器、`client` fixture、`add_giveaway()` 與 `join()`。"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import discord
import pytest
from fastapi.testclient import TestClient

from starlib import sclient
from starlib.database import Giveaway, GiveawayUser
from starlib.utils import nowtz
from starServer.dashboard import giveaways
from tests.helpers.dashboard_auth import make_app, make_session
from tests.helpers.dashboard_guilds import MANAGE_MESSAGES, g
from tests.helpers.dashboard_notifies import GUILD_ID, fake_bot

CREATOR = 7001
MEMBER = 7002
LEFT = 7003
ALL_PERMS = discord.Permissions(view_channel=True, read_message_history=True, send_messages=True)


class FakeChannel:
    def __init__(self, name: str, perms: discord.Permissions):
        self.name = name
        self.perms = perms

    def permissions_for(self, member):
        return self.perms


class FakeGuild:
    def __init__(self):
        self.id = GUILD_ID
        self.members = {
            CREATOR: SimpleNamespace(display_name="發起人", display_avatar=SimpleNamespace(url="https://cdn/c.png")),
            MEMBER: SimpleNamespace(display_name="成員", display_avatar=SimpleNamespace(url="https://cdn/m.png")),
        }
        self.me = SimpleNamespace(display_name="bot")
        self.channels = {500: FakeChannel("抽獎頻道", ALL_PERMS)}

    def get_member(self, uid: int):
        return self.members.get(uid)

    def get_channel_or_thread(self, cid: int):
        return self.channels.get(cid)


@pytest.fixture
def client(discord_env, repo, dashboard_env, monkeypatch) -> TestClient:
    make_session(repo)
    discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_MESSAGES)]
    monkeypatch.setattr(giveaways, "sqldb", repo)
    guild = FakeGuild()
    bot = fake_bot(guild)
    bot.get_user = lambda uid: None
    monkeypatch.setattr(sclient, "bot", bot)
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
    c.cookies.set("dashboard_session", "sid")
    c.guild = guild  # pyright: ignore[reportAttributeAccessIssue]
    c.repo = repo  # pyright: ignore[reportAttributeAccessIssue]
    c.discord_env = discord_env  # pyright: ignore[reportAttributeAccessIssue]
    c.monkeypatch = monkeypatch  # pyright: ignore[reportAttributeAccessIssue]
    return c


def add_giveaway(
    client, *, prize="獎品", guild_id=GUILD_ID, is_on=False, created_days_ago=1, ended_days_ago=0
) -> Giveaway:
    now = nowtz().replace(microsecond=0)
    row = Giveaway(
        guild_id=guild_id,
        channel_id=500,
        message_id=900,
        creator_id=CREATOR,
        prize_name=prize,
        winner_count=1,
        created_at=now - timedelta(days=created_days_ago),
        end_at=(now + timedelta(hours=2)) if is_on else (now - timedelta(days=ended_days_ago)),
        is_on=is_on,
        description=None,
        redraw_count=0,
    )
    client.repo.add(row)
    return row


def join(client, giveaway_id: int, user_id: int, winner: bool = False, minutes: int = 0):
    join_at = nowtz().replace(microsecond=0) + timedelta(minutes=minutes)
    client.repo.add(
        GiveawayUser(giveaway_id=giveaway_id, user_id=user_id, user_weight=1, join_at=join_at, is_winner=winner)
    )
