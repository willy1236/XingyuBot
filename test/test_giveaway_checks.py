"""抽獎建立前的權限檢查與到期開獎沒公告到時的紀錄。"""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import discord
import pytest

from starDiscord.uiElement.view import GiveawayOutcome, GiveawayView

FULL = discord.Permissions(
    view_channel=True, read_message_history=True, send_messages=True, send_messages_in_threads=True
)


class TestMissingPermissions:
    def test_full_permissions(self):
        assert GiveawayView.missing_permissions(object(), FULL) == []

    def test_no_view_channel(self):
        perms = discord.Permissions(read_message_history=True, send_messages=True)
        assert GiveawayView.missing_permissions(object(), perms) == ["檢視頻道"]

    def test_lists_all_missing(self):
        assert GiveawayView.missing_permissions(object(), discord.Permissions.none()) == [
            "檢視頻道",
            "讀取訊息歷史",
            "發送訊息",
        ]

    def test_thread_needs_send_in_threads(self):
        thread = object.__new__(discord.Thread)
        perms = discord.Permissions(view_channel=True, read_message_history=True, send_messages=True)
        assert GiveawayView.missing_permissions(thread, perms) == ["在討論串發送訊息"]


class TestAutoEndLogging:
    def run(self, monkeypatch, outcome: GiveawayOutcome):
        view = object.__new__(GiveawayView)
        view.giveaway = SimpleNamespace(id=3)

        async def finish():
            return outcome

        monkeypatch.setattr(view, "finish", finish)
        asyncio.run(view.auto_end())

    @pytest.mark.parametrize("outcome", [GiveawayOutcome("ok"), GiveawayOutcome("already_ended")])
    def test_success_is_silent(self, monkeypatch, caplog, outcome):
        with caplog.at_level(logging.ERROR):
            self.run(monkeypatch, outcome)
        assert not caplog.records

    @pytest.mark.parametrize("outcome", [GiveawayOutcome("ok", "no_permission"), GiveawayOutcome("not_found")])
    def test_failure_logs_error(self, monkeypatch, caplog, outcome):
        with caplog.at_level(logging.ERROR):
            self.run(monkeypatch, outcome)
        [record] = caplog.records
        assert record.giveaway_id == 3
        assert record.status == outcome.status
        assert record.announce_failure == outcome.announce_failure
