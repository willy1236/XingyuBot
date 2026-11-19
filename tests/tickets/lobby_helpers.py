"""客服單大廳測試共用：假 bot、伺服器、頻道與 `add_ticket()`。"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import discord
import pytest

from starDiscord import ticket_lobby
from starlib import sclient
from starlib.database import TicketChannel

GUILD_ID = 8_800_000_000_000_001
LOBBY_A = 8_800_000_000_000_011
LOBBY_NEW = 8_800_000_000_000_012
CATEGORY_TICKET = 8_800_000_000_000_021
CATEGORY_OWN = 8_800_000_000_000_022
OLD_MESSAGE = 8_800_000_000_000_031


T1, T2 = 8_800_000_000_000_041, 8_800_000_000_000_042


ROLE_1, ROLE_2 = 8_800_000_000_000_051, 8_800_000_000_000_052


CREATED = datetime(2026, 1, 1, tzinfo=UTC)


def http_error(status=500):
    return discord.HTTPException(SimpleNamespace(status=status, reason="boom"), "boom")


def not_found():
    return discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "unknown")


class FakeMessage:
    def __init__(self, mid: int, content: str | None = "舊"):
        self.id = mid
        self.content = content
        self.embeds: list = []
        self.edits: list[dict] = []
        self.deleted = False
        self.fail_edit = False
        self.view = None

    @property
    def jump_url(self) -> str:
        return f"https://discord.com/channels/{GUILD_ID}/x/{self.id}"

    async def edit(self, **kwargs):
        if self.fail_edit:
            raise http_error()
        await asyncio.sleep(0)  # 讓同時進行的流程有機會交錯
        self.edits.append(kwargs)
        if "content" in kwargs:
            self.content = kwargs["content"]
        if "embeds" in kwargs:
            self.embeds = list(kwargs["embeds"])
        if "view" in kwargs:
            self.view = kwargs["view"]

    async def delete(self, *, reason=None):
        self.deleted = True


class FakeChannel:
    def __init__(self, cid: int, kind=discord.ChannelType.text, category_id: int | None = CATEGORY_OWN):
        self.id = cid
        self.type = kind
        self.category_id = category_id
        self.messages: dict[int, FakeMessage] = {}
        self.sent: list[tuple[FakeMessage, dict]] = []
        self.fail_send = False
        self.deleted = False
        self.permission_calls: list[tuple[int, object, str | None]] = []
        self.next_id = 8_800_000_000_000_900

    async def fetch_message(self, mid: int):
        if mid not in self.messages:
            raise not_found()
        return self.messages[mid]

    async def send(self, **kwargs):
        if self.fail_send:
            raise http_error(403)
        self.next_id += 1
        m = FakeMessage(self.next_id, kwargs.get("content"))
        self.messages[m.id] = m
        self.sent.append((m, kwargs))
        return m

    async def set_permissions(self, role, *, overwrite, reason=None):
        self.permission_calls.append((role.id, overwrite, reason))

    async def delete(self, *, reason=None):
        self.deleted = True
        self.delete_reason = reason


class FakeGuild:
    def __init__(self):
        self.id = GUILD_ID
        self.me = SimpleNamespace(id=1, display_avatar=SimpleNamespace(url="https://cdn/bot.png"))
        self.lobby = FakeChannel(LOBBY_A)
        self.ticket_category = FakeChannel(CATEGORY_TICKET, kind=discord.ChannelType.category, category_id=None)
        self.channels = {c.id: c for c in (self.lobby, self.ticket_category)}
        self.roles = {r: SimpleNamespace(id=r) for r in (ROLE_1, ROLE_2)}
        self.created: list[tuple[str, dict]] = []

    def get_channel(self, cid):
        return self.channels.get(cid)

    def get_role(self, rid):
        return self.roles.get(rid)

    async def create_text_channel(self, name, **kwargs):
        if getattr(self, "fail_create", False):
            raise http_error(403)
        c = FakeChannel(LOBBY_NEW)
        self.channels[c.id] = c
        self.created.append((name, kwargs))
        return c


class FakeBot:
    def __init__(self):
        self.views: list[tuple[int | None, discord.ui.View]] = []

    def add_view(self, view, message_id=None):
        self.views.append((message_id, view))


@pytest.fixture
def env(repo, monkeypatch):
    monkeypatch.setattr(ticket_lobby, "sqldb", repo)
    # 鎖綁定第一次發生等待時的事件迴圈；每個測試用自己的迴圈，所以每次換一組鎖
    monkeypatch.setattr(ticket_lobby, "_locks", {})
    bot = FakeBot()
    monkeypatch.setattr(sclient, "bot", bot)
    return SimpleNamespace(guild=FakeGuild(), bot=bot, repo=repo)


def add_ticket(env, cid, *, closed=False, saved=None):
    env.repo.merge(
        TicketChannel(
            channel_id=cid,
            guild_id=env.guild.id,
            creator_id=7,
            created_at=CREATED,
            closed_at=CREATED if closed else None,
            closer_id=8 if closed else None,
            lobby_channel_id=LOBBY_A,
            locked_overwrites_json=None if saved is None else json.dumps(saved),
        )
    )
    env.guild.channels[cid] = FakeChannel(cid)
