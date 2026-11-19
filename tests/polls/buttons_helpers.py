"""投票按鈕測試共用的假 Interaction。"""

from __future__ import annotations

from types import SimpleNamespace

import discord

from tests.polls.core_helpers import (
    CREATOR,
    fake_chart,  # noqa: F401  (fixture)
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
