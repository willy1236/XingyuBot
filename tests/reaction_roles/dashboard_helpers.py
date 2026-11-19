"""後台反應身分組測試共用的身分組與頻道常數。"""

from __future__ import annotations

from types import SimpleNamespace

import discord

from tests.helpers.dashboard_notifies import GUILD_ID

ALL_PERMS = dict(view_channel=True, send_messages=True, embed_links=True, read_message_history=True)
BOT_TOP = 10
ROLE_OK = 3001
ROLE_ABOVE = 3002
ROLE_MANAGED = 3003
ROLE_GONE = 3999
EVERYONE = GUILD_ID


class FakeChannel:
    def __init__(self, cid: int, name: str, position: int, category_position: int | None = None, **perms):
        self.id = cid
        self.name = name
        self.position = position
        self.category = SimpleNamespace(position=category_position) if category_position is not None else None
        self.perms = {**ALL_PERMS, **perms}
        self.messages: dict[int, discord.Message | SimpleNamespace] = {}
        self.forbidden = False

    def permissions_for(self, _member):
        return SimpleNamespace(**self.perms)

    async def fetch_message(self, mid: int):
        if getattr(self, "fetch_error", None) is not None:
            raise self.fetch_error
        if self.forbidden:
            raise discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "missing access")
        if mid not in self.messages:
            raise discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "unknown message")
        return self.messages[mid]
