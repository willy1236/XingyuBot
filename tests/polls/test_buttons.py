"""投票 V-02：投票被刪除後，留在 Discord 上的按鈕回「此投票已不存在」（假 Discord，真實 PostgreSQL）。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import discord
import pytest

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
from tests.polls.buttons_helpers import FakeInteraction
from tests.polls.core_helpers import (
    FakeBot,
    add_poll,
    fake_chart,  # noqa: F401  (fixture)
    http_error,
)


def press(repo, poll, button_type, interaction, *, delete: bool = False):
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
def test_deleted_poll_replies_gone_and_strips_buttons(repo, button_type):
    poll = add_poll(repo)
    interaction = FakeInteraction()
    press(repo, poll, button_type, interaction, delete=True)
    followups = interaction.followups
    assert interaction.sent == [(POLL_GONE_TEXT, True)]
    assert followups == []
    assert interaction.stripped == 1


def test_strip_failure_is_ignored(repo):
    poll = add_poll(repo)
    interaction = FakeInteraction(strip_error=http_error(discord.Forbidden, 403))
    press(repo, poll, PollNowButton, interaction, delete=True)
    assert interaction.sent == [(POLL_GONE_TEXT, True)]


def test_already_responded_interaction_is_ignored(repo):
    poll = add_poll(repo)
    interaction = FakeInteraction(already_responded=True)
    press(repo, poll, PollResultButton, interaction, delete=True)
    assert interaction.sent == []


def test_existing_poll_is_not_affected(repo):
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


def test_embed_author_without_custom_avatar(repo):
    """發起人沒有自訂頭像（avatar 為 None）時，embed 改用預設頭像，不會 AttributeError"""
    poll = add_poll(repo)
    member = SimpleNamespace(name="發起人", avatar=None, display_avatar=SimpleNamespace(url="https://cdn/default.png"))
    guild = SimpleNamespace(get_member=lambda uid: member, get_role=lambda rid: None)

    async def go():
        return PollView(poll, repo, FakeBot(None)).embed(guild)  # type: ignore[arg-type]

    embed = asyncio.run(go())
    assert embed.author.name == "發起人"
    assert embed.author.icon_url == "https://cdn/default.png"
