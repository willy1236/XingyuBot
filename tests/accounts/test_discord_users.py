"""後台的 Discord 使用者查詢：bot 快取優先，向 Discord 查到的結果保留 10 分鐘。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from starlib import sclient
from starServer.dashboard import discord_users
from starServer.dashboard.discord_users import DiscordProfile, fetch_discord_user
from tests.helpers.accounts import FakeBot


class CountingBot(FakeBot):
    def __init__(self, users, cached=()):
        super().__init__(users)
        self.cached = set(cached)
        self.fetches = 0

    def get_user(self, uid):
        return self._user(uid) if uid in self.cached else None

    async def fetch_user(self, uid):
        self.fetches += 1
        return await super().fetch_user(uid)


@pytest.fixture
def clock(monkeypatch):
    c = SimpleNamespace(now=1000.0)
    monkeypatch.setattr(discord_users, "time", SimpleNamespace(monotonic=lambda: c.now))
    monkeypatch.setattr(discord_users, "_fetched", {})
    return c


def fetch(uid):
    return asyncio.run(fetch_discord_user(uid))


def test_fetched_user_cached_for_10_minutes(monkeypatch, clock):
    bot = CountingBot({1: ("One", "abc")})
    monkeypatch.setattr(sclient, "bot", bot)
    assert fetch(1) == DiscordProfile("One", "abc")
    clock.now += 599
    assert fetch(1) == DiscordProfile("One", "abc")
    assert bot.fetches == 1
    clock.now += 2
    fetch(1)
    assert bot.fetches == 2


def test_bot_cache_needs_no_fetch(monkeypatch, clock):
    bot = CountingBot({1: ("One", None)}, cached={1})
    monkeypatch.setattr(sclient, "bot", bot)
    assert fetch(1) == DiscordProfile("One", None)
    assert bot.fetches == 0 and discord_users._fetched == {}


def test_failure_not_cached(monkeypatch, clock):
    bot = CountingBot({})
    monkeypatch.setattr(sclient, "bot", bot)
    assert fetch(1) is None
    assert fetch(1) is None
    assert bot.fetches == 2


def test_without_bot(monkeypatch, clock):
    monkeypatch.setattr(sclient, "bot", None)
    assert fetch(1) is None
