"""後台設定頁測試共用的假伺服器：頻道、身分組常數與 `fake_bot()`、`fake_guild()`。"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import discord

GUILD_ID = 1001
OK_CHANNEL = 11
VOICE_CHANNEL = 12
NO_SEND_CHANNEL = 13
NO_HISTORY_CHANNEL = 14
OK_ROLE = 21
LOCKED_ROLE = 22
MANAGED_ROLE = 23


def perms(**missing: bool) -> SimpleNamespace:
    values = dict(view_channel=True, send_messages=True, embed_links=True, read_message_history=True)
    values.update({k: False for k in missing})
    return SimpleNamespace(**values)


def channel(cid: int, name: str, type=discord.ChannelType.text, **missing) -> SimpleNamespace:
    p = perms(**missing)
    return SimpleNamespace(id=cid, name=name, type=type, permissions_for=lambda _me: p)


def role(rid: int, name: str, *, mentionable=True, managed=False, default=False) -> SimpleNamespace:
    return SimpleNamespace(id=rid, name=name, mentionable=mentionable, managed=managed, is_default=lambda: default)


def fake_guild(mention_everyone: bool = False) -> SimpleNamespace:
    channels = {
        c.id: c
        for c in (
            channel(OK_CHANNEL, "general"),
            channel(VOICE_CHANNEL, "voice", discord.ChannelType.voice),
            channel(NO_SEND_CHANNEL, "locked", send_messages=True),
            channel(NO_HISTORY_CHANNEL, "nohistory", read_message_history=True),
            channel(15, "news", discord.ChannelType.news),
        )
    }
    roles = {
        r.id: r
        for r in (
            role(OK_ROLE, "ping"),
            role(LOCKED_ROLE, "locked", mentionable=False),
            role(MANAGED_ROLE, "bot-role", managed=True),
            role(GUILD_ID, "@everyone", default=True),
        )
    }
    me = SimpleNamespace(guild_permissions=SimpleNamespace(mention_everyone=mention_everyone))
    return SimpleNamespace(id=GUILD_ID, me=me, get_channel=channels.get, get_role=roles.get)


def fake_bot(guild=None, ready: bool = True):
    pool = ThreadPoolExecutor(max_workers=1)
    return SimpleNamespace(
        is_ready=lambda: ready,
        get_guild=lambda gid: guild if gid == GUILD_ID else None,
        submit=lambda coro: pool.submit(asyncio.run, coro),
    )
