"""投票 V-02：投票被刪除後，留在 Discord 上的按鈕回「此投票已不存在」（假 Discord，真實 PostgreSQL）。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import discord
import pytest
from test_dashboard_polls_core import CREATOR, FakeBot, add_poll, fake_chart, http_error  # noqa: F401
from test_identity import repo  # noqa: F401

from starDiscord.uiElement.view import (
    POLL_GONE_TEXT,
    PollCanenlButton,
    PollEndButton,
    PollNowButton,
    PollOptionButton,
    PollResultButton,
    PollView,
    reply_poll_gone,
)


class FakeInteraction:
    def __init__(self, *, strip_error: Exception | None = None, already_responded: bool = False):
        self.sent: list[tuple[str, bool]] = []
        self.followups: list[str] = []
        self.stripped = 0
        self.user = SimpleNamespace(id=CREATOR, mention="@u", get_role=lambda rid: None)
        self.guild = None
        self.already_responded = already_responded
        self.strip_error = strip_error
        self.response = SimpleNamespace(send_message=self._send, defer=self._defer)
        self.followup = SimpleNamespace(send=self._followup)
        self.message = SimpleNamespace(edit=self._edit)

    async def _send(self, text, ephemeral=False, **kwargs):
        if self.already_responded:
            raise discord.InteractionResponded(SimpleNamespace())  # type: ignore[arg-type]
        self.sent.append((text, ephemeral))

    async def _defer(self):
        pass

    async def _followup(self, text, ephemeral=False):
        self.followups.append(text)

    async def _edit(self, **kwargs):
        assert kwargs == {"view": None}
        self.stripped += 1
        if self.strip_error:
            raise self.strip_error


def press(repo, poll, button_type, interaction, *, delete: bool = False):  # noqa: F811
    """按下按鈕；delete 為 True 時，view 建好（模擬已註冊的長駐 view）後才刪除投票"""

    async def go():
        view = PollView(poll, repo, FakeBot(None))  # type: ignore[arg-type]
        button = next(c for c in view.children if isinstance(c, button_type))
        if delete:
            repo.delete_poll(poll.poll_id)
        await button.callback(interaction)

    asyncio.run(go())


BUTTONS = [PollOptionButton, PollEndButton, PollResultButton, PollCanenlButton, PollNowButton]


@pytest.mark.parametrize("button_type", BUTTONS)
def test_deleted_poll_replies_gone_and_strips_buttons(repo, button_type):  # noqa: F811
    poll = add_poll(repo)
    interaction = FakeInteraction()
    press(repo, poll, button_type, interaction, delete=True)
    followups = interaction.followups
    assert interaction.sent == [(POLL_GONE_TEXT, True)]
    assert followups == []
    assert interaction.stripped == 1


def test_strip_failure_is_ignored(repo):  # noqa: F811
    poll = add_poll(repo)
    interaction = FakeInteraction(strip_error=http_error(discord.Forbidden, 403))
    press(repo, poll, PollNowButton, interaction, delete=True)
    assert interaction.sent == [(POLL_GONE_TEXT, True)]


def test_already_responded_interaction_is_ignored(repo):  # noqa: F811
    poll = add_poll(repo)
    interaction = FakeInteraction(already_responded=True)
    press(repo, poll, PollResultButton, interaction, delete=True)
    assert interaction.sent == []


def test_existing_poll_is_not_affected(repo):  # noqa: F811
    poll = add_poll(repo)
    interaction = FakeInteraction()
    press(repo, poll, PollNowButton, interaction)
    assert interaction.stripped == 0
    assert POLL_GONE_TEXT not in [t for t, _ in interaction.sent]


def test_reply_poll_gone_without_message():
    interaction = FakeInteraction()
    interaction.message = None
    asyncio.run(reply_poll_gone(interaction))  # type: ignore[arg-type]
    assert interaction.sent == [(POLL_GONE_TEXT, True)]
