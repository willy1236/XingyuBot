"""scripts/backfill_ticket_lobby.py：把測試版私人頻道依分類歸屬到大廳（P-01）。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import discord

from scripts import backfill_ticket_lobby
from scripts.backfill_ticket_lobby import plan_backfill

GUILD = 1
OTHER_GUILD = 2


def lobby(cid: int, category: int | None, guild: int = GUILD, removed: bool = False):
    return SimpleNamespace(
        channel_id=cid,
        guild_id=guild,
        ticket_category_id=category,
        removed_at=datetime(2026, 1, 1, tzinfo=UTC) if removed else None,
    )


def ticket(cid: int, guild: int = GUILD, lobby_channel_id: int | None = None):
    return SimpleNamespace(channel_id=cid, guild_id=guild, lobby_channel_id=lobby_channel_id)


class TestPlanBackfill:
    def test_unique_lobby_by_category(self):
        plan = plan_backfill([lobby(10, 100), lobby(11, 101)], [ticket(1), ticket(2)], {1: 100, 2: 101})
        assert plan == {1: 10, 2: 11}

    def test_no_matching_lobby_stays_unassigned(self):
        assert plan_backfill([lobby(10, 100)], [ticket(1)], {1: 999}) == {}

    def test_multiple_lobbies_same_category_stays_unassigned(self):
        assert plan_backfill([lobby(10, 100), lobby(11, 100)], [ticket(1)], {1: 100}) == {}

    def test_removed_lobby_not_counted(self):
        """已移除的大廳不參與：唯一的未移除大廳仍可歸屬；只剩已移除的則對不到"""
        assert plan_backfill([lobby(10, 100), lobby(11, 100, removed=True)], [ticket(1)], {1: 100}) == {1: 10}
        assert plan_backfill([lobby(11, 100, removed=True)], [ticket(1)], {1: 100}) == {}

    def test_other_guild_lobby_not_matched(self):
        assert plan_backfill([lobby(10, 100, guild=OTHER_GUILD)], [ticket(1)], {1: 100}) == {}

    def test_lobby_without_category_not_matched(self):
        assert plan_backfill([lobby(10, None)], [ticket(1)], {1: None}) == {}

    def test_deleted_or_uncategorized_channel_skipped(self):
        assert plan_backfill([lobby(10, 100)], [ticket(1), ticket(2)], {2: None}) == {}

    def test_already_assigned_untouched(self):
        assert plan_backfill([lobby(10, 100)], [ticket(1, lobby_channel_id=99)], {1: 100}) == {}


class FakeClient:
    """假的 discord.Client：bot 只在 GUILD 這個伺服器；頻道 1 存在，2 被刪除"""

    def __init__(self, *args, **kwargs):
        self.fetched: list[int] = []

    async def login(self, token):
        pass

    async def close(self):
        pass

    async def fetch_guilds(self, **kwargs):
        yield SimpleNamespace(id=GUILD)

    async def fetch_channel(self, cid: int):
        self.fetched.append(cid)
        if cid == 2:
            raise discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "unknown channel")
        return SimpleNamespace(category_id=100)


class TestFetchCategories:
    def test_skips_guilds_the_bot_is_not_in_and_deleted_channels(self, monkeypatch, capsys):
        client = FakeClient()
        monkeypatch.setattr(backfill_ticket_lobby.discord, "Client", lambda **kw: client)
        tickets = [ticket(1), ticket(2), ticket(3, guild=OTHER_GUILD)]
        result = asyncio.run(backfill_ticket_lobby.fetch_categories("token", tickets))
        assert result == {1: 100}
        assert client.fetched == [1, 2]  # 別的伺服器的紀錄不打 API
        out = capsys.readouterr().out
        assert "3（伺服器 2）：這個 bot 不在該伺服器" in out
        assert "2（伺服器 1）：頻道已不存在" in out
