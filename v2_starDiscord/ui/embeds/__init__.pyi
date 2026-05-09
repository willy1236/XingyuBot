# __init__.pyi ────────────────────────────────────────────────────────────────
# 此檔案由 tools/gen_embed_stubs.py 自動生成，請勿手動編輯。
# 重新生成：python tools/gen_embed_stubs.py
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

from typing import overload

import discord

from v2_starDiscord.ui.embeds.base import BotEmbed as BotEmbed
from v2_starDiscord.ui.embeds.base import EmptyContext as EmptyContext
from v2_starDiscord.ui.embeds.postgresql import UserModerateCtx as UserModerateCtx
from v2_starlib.database.postgresql.models import BackupRole as BackupRole
from v2_starlib.database.postgresql.models import UserModerate as UserModerate

# 已收錄模型：BackupRole, UserModerate
# 已收錄 Context：EmptyContext, UserModerateCtx


class BotEmbed:
    # ── UserModerate ──
    @classmethod
    @overload
    def to_embed(cls, data: UserModerate, ctx: UserModerateCtx) -> discord.Embed: ...
    @classmethod
    @overload
    def to_embed(cls, data: list[UserModerate], ctx: UserModerateCtx) -> discord.Embed: ...
    @classmethod
    @overload
    def to_embeds(cls, data: UserModerate, ctx: UserModerateCtx) -> list[discord.Embed]: ...
    @classmethod
    @overload
    def to_embeds(cls, data: list[UserModerate], ctx: UserModerateCtx) -> list[discord.Embed]: ...

    # ── BackupRole ──
    @classmethod
    @overload
    def to_embed(cls, data: BackupRole, ctx: EmptyContext) -> discord.Embed: ...
    @classmethod
    @overload
    def to_embed(cls, data: list[BackupRole], ctx: EmptyContext) -> discord.Embed: ...
    @classmethod
    @overload
    def to_embeds(cls, data: BackupRole, ctx: EmptyContext) -> list[discord.Embed]: ...
    @classmethod
    @overload
    def to_embeds(cls, data: list[BackupRole], ctx: EmptyContext) -> list[discord.Embed]: ...

    # ── fallback ──
    @classmethod
    @overload
    def to_embed(cls, data: object, ctx: EmptyContext = ...) -> discord.Embed: ...
    @classmethod
    @overload
    def to_embeds(cls, data: object, ctx: EmptyContext = ...) -> list[discord.Embed]: ...


