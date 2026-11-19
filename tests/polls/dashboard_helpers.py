"""後台投票列表與詳情測試共用：假伺服器、`client` fixture、`add_poll()` 與 `vote()`。"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace

import discord
import pytest
from fastapi.testclient import TestClient

from starlib import sclient
from starlib.database import Poll
from starlib.utils import nowtz
from starServer.dashboard import polls
from tests.helpers.dashboard_auth import USER_ID, make_app, make_session
from tests.helpers.dashboard_guilds import MANAGE_MESSAGES, g
from tests.helpers.dashboard_notifies import GUILD_ID

URL = f"/dashboard/guilds/{GUILD_ID}/polls"
VIEWER = int(USER_ID)
CREATOR = 7001
MEMBER = 7002
LEFT = 7003
OTHER_GUILD = 2002
ALL_PERMS = discord.Permissions(view_channel=True, read_message_history=True, send_messages=True)
NO_HISTORY = discord.Permissions(view_channel=True, send_messages=True)


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
            uid: SimpleNamespace(display_name=name)
            for uid, name in {CREATOR: "發起人", MEMBER: "成員", VIEWER: "管理員"}.items()
        }
        self.me = SimpleNamespace(display_name="bot")
        self.channels = {500: FakeChannel("投票頻道", ALL_PERMS), 501: FakeChannel("缺權限頻道", NO_HISTORY)}
        self.roles = {600: SimpleNamespace(name="成員身分組")}

    def get_member(self, uid: int):
        return self.members.get(uid)

    def get_role(self, rid: int):
        return self.roles.get(rid)

    def get_channel_or_thread(self, cid: int):
        return self.channels.get(cid)


class FakeBot:
    def __init__(self, guild: FakeGuild):
        self.guild = guild
        self.owner_ids: set[int] = set()
        self._pool = ThreadPoolExecutor(max_workers=1)

    def is_ready(self) -> bool:
        return True

    def get_guild(self, gid: int):
        return self.guild if gid == GUILD_ID else None

    def submit(self, coro):
        return self._pool.submit(asyncio.run, coro)

    async def is_owner(self, user) -> bool:
        return user.id in self.owner_ids


@pytest.fixture
def client(discord_env, repo, dashboard_env, monkeypatch) -> TestClient:
    make_session(repo)
    discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_MESSAGES)]
    monkeypatch.setattr(polls, "sqldb", repo)
    guild = FakeGuild()
    bot = FakeBot(guild)
    monkeypatch.setattr(sclient, "bot", bot)
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
    c.cookies.set("dashboard_session", "sid")
    c.guild = guild  # pyright: ignore[reportAttributeAccessIssue]
    c.bot = bot  # pyright: ignore[reportAttributeAccessIssue]
    c.repo = repo  # pyright: ignore[reportAttributeAccessIssue]
    c.discord_env = discord_env  # pyright: ignore[reportAttributeAccessIssue]
    return c


def add_poll(
    client,
    *,
    title="投票",
    options=("甲", "乙"),
    guild_id=GUILD_ID,
    ended=False,
    created_days_ago=1,
    ended_days_ago=0,
    channel_id: int | None = 500,
    creator_id=CREATOR,
    show_name=True,
    check=True,
    only_initiator=False,
    ban_alt=False,
) -> Poll:
    now = nowtz().replace(microsecond=0)
    poll = Poll(
        title=title,
        creator_id=creator_id,
        created_at=now - timedelta(days=created_days_ago),
        guild_id=guild_id,
        channel_id=channel_id,
        message_id=900 if channel_id is not None else 123,
        end_at=(now - timedelta(days=ended_days_ago)) if ended else None,
        number_of_user_votes=1,
        ban_alternate_account_voting=ban_alt,
        show_name=show_name,
        check_results_in_advance=check,
        results_only_initiator=only_initiator,
        can_change_vote=None,
    )
    client.repo.add(poll)
    client.repo.add_poll_option(poll.poll_id, list(options))
    return poll


def vote(client, poll: Poll, user_id: int, option_id: int, weight: int = 1, minutes: int = 0):
    client.repo.add_user_poll(
        poll.poll_id, user_id, option_id, nowtz().replace(microsecond=0) + timedelta(minutes=minutes), weight
    )
