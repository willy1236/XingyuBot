"""投票 V-02：bot 重啟後，已刪除投票留下的按鈕由 on_interaction 回「此投票已不存在」（假 Discord，真實 PostgreSQL）。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import discord
import pytest
from test_dashboard_polls_buttons import FakeInteraction
from test_dashboard_polls_core import add_poll
from test_identity import repo  # noqa: F401

from starDiscord.cmds import bot_event
from starDiscord.cmds.bot_event import event, poll_id_of_button
from starDiscord.uiElement.view import POLL_GONE_TEXT


@pytest.mark.parametrize(
    ("custom_id", "expected"),
    [
        ("poll_12_3", 12),
        ("poll_result_12", 12),
        ("end_poll_12", 12),
        ("vote_canenl_12", 12),
        ("vote_now_12", 12),
        ("poll_result_", None),
        ("poll_12", None),
        ("poll_12_3_4", None),
        ("giveaway_join_12", None),
        ("ticket_lock_12", None),
        ("", None),
        (None, None),
    ],
)
def test_poll_id_of_button(custom_id, expected):
    assert poll_id_of_button(custom_id) == expected


def interact(repo, monkeypatch, custom_id: str, *, interaction: FakeInteraction | None = None, view=None, kind=discord.InteractionType.component):  # noqa: F811
    monkeypatch.setattr(bot_event.sclient, "sqldb", repo)
    interaction = interaction or FakeInteraction()
    interaction.type = kind  # type: ignore[attr-defined]
    interaction.view = view  # type: ignore[attr-defined]
    interaction.data = {"custom_id": custom_id}  # type: ignore[attr-defined]
    interaction.response.is_done = lambda: interaction.sent != []  # type: ignore[attr-defined]
    cog = event(SimpleNamespace())  # type: ignore[arg-type]
    asyncio.run(cog.on_interaction(interaction))  # type: ignore[arg-type]
    return interaction


@pytest.mark.parametrize("custom_id", ["poll_{id}_1", "poll_result_{id}", "end_poll_{id}", "vote_canenl_{id}", "vote_now_{id}"])
def test_deleted_poll_button_gets_gone_reply(repo, monkeypatch, custom_id):  # noqa: F811
    poll = add_poll(repo)
    repo.delete_poll(poll.poll_id)
    i = interact(repo, monkeypatch, custom_id.format(id=poll.poll_id))
    assert i.sent == [(POLL_GONE_TEXT, True)]
    assert i.stripped == 1


def test_existing_poll_is_left_alone(repo, monkeypatch):  # noqa: F811
    poll = add_poll(repo)
    i = interact(repo, monkeypatch, f"vote_now_{poll.poll_id}")
    assert i.sent == [] and i.stripped == 0


def test_interaction_taken_by_a_view_is_skipped_without_querying(repo, monkeypatch):  # noqa: F811
    monkeypatch.setattr(repo, "get_poll_fresh", lambda pid: pytest.fail("不該查資料庫"))
    i = interact(repo, monkeypatch, "vote_now_999999", view=object())
    assert i.sent == []


def test_already_responded_interaction_is_skipped(repo, monkeypatch):  # noqa: F811
    i = FakeInteraction()
    i.sent.append(("x", True))
    interact(repo, monkeypatch, "vote_now_999999", interaction=i)
    assert i.sent == [("x", True)]


def test_not_a_poll_button_is_skipped(repo, monkeypatch):  # noqa: F811
    i = interact(repo, monkeypatch, "giveaway_join_999999")
    assert i.sent == []


def test_non_component_interaction_is_skipped(repo, monkeypatch):  # noqa: F811
    i = interact(repo, monkeypatch, "vote_now_999999", kind=discord.InteractionType.application_command)
    assert i.sent == []
