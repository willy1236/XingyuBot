"""投票核心流程測試共用：假 Discord 訊息與頻道、`add_poll()`，以及替換圖表產生的 autouse fixture。"""

from __future__ import annotations

import io
from datetime import timedelta
from types import SimpleNamespace

import discord
import pytest

from starDiscord.uiElement.view import PollView
from starlib.database import Poll
from starlib.utils import nowtz

GUILD_ID = 1001
CHANNEL_ID = 500
MESSAGE_ID = 900
CREATOR = 7001


@pytest.fixture(autouse=True)
def fake_chart(monkeypatch):
    """圓餅圖的繪製不在這裡測；matplotlib 的視窗後端在無 Tk 的環境會失敗"""
    monkeypatch.setattr(PollView, "generate_chart", lambda self, labels, sizes: io.BytesIO(b"png"))


def http_error(cls, status: int):
    return cls(SimpleNamespace(status=status, reason="error"), "error")


class FakeMessage:
    def __init__(self, error: Exception | None = None):
        self.id = MESSAGE_ID
        self.edits: list[dict] = []
        self.error = error

    async def edit(self, **kwargs):
        if self.error:
            raise self.error
        self.edits.append(kwargs)


class FakeChannel:
    def __init__(self, message: FakeMessage | None, fetch_error: Exception | None = None):
        self.message = message
        self.fetch_error = fetch_error

    async def fetch_message(self, mid: int):
        if self.fetch_error:
            raise self.fetch_error
        if self.message is None:
            raise http_error(discord.NotFound, 404)
        return self.message


class FakeGuild:
    def __init__(self, channel: FakeChannel | None):
        self.channel = channel

    def get_member(self, uid: int):
        return None

    def get_channel_or_thread(self, cid: int):
        return self.channel if cid == CHANNEL_ID else None


class FakeBot:
    def __init__(self, channel: FakeChannel | None):
        self.guild = FakeGuild(channel)
        self.fetched = 0

    def get_guild(self, gid: int):
        return self.guild if gid == GUILD_ID else None

    async def fetch_channel(self, cid: int):
        self.fetched += 1
        raise http_error(discord.NotFound, 404)


def add_poll(repo, *, channel_id: int | None = CHANNEL_ID, created_days_ago=1, votes=True) -> Poll:
    poll = Poll(
        title="投票",
        creator_id=CREATOR,
        created_at=nowtz().replace(microsecond=0) - timedelta(days=created_days_ago),
        guild_id=GUILD_ID,
        channel_id=channel_id,
        message_id=MESSAGE_ID,
        end_at=None,
        number_of_user_votes=1,
        ban_alternate_account_voting=False,
        show_name=True,
        check_results_in_advance=True,
        results_only_initiator=False,
        can_change_vote=None,
    )
    repo.add(poll)
    repo.add_poll_option(poll.poll_id, ["甲", "乙"])
    if votes:
        repo.add_user_poll(poll.poll_id, 1, 1, nowtz().replace(microsecond=0), 2)
        repo.add_user_poll(poll.poll_id, 2, 2, nowtz().replace(microsecond=0), 1)
    return poll


def stored(repo, poll_id: int) -> Poll:
    repo.session.expire_all()
    return repo.get_poll(poll_id)
