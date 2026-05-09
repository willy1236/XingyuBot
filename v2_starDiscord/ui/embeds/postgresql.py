# embeds/postgresql.py ───────────────────────────────────────────────────────
from __future__ import annotations

from dataclasses import dataclass

import discord

from v2_starlib.database.postgresql.models import (
    BackupCategory,
    BackupChannel,
    BackupMessage,
    BackupRole,
    HappycampApplicationForm,
    UserModerate,
)
from v2_starlib.fileDatabase import JsonDatabase

from .base import BaseTransformer, EmbedFactory, EmptyContext

# ── Contexts ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class UserModerateCtx:
    Jsondb: JsonDatabase


# ── Transformers ─────────────────────────────────────────────────────────────


@EmbedFactory.register_decorator(UserModerate)
class UserModerateTransformer(BaseTransformer[UserModerate, UserModerateCtx]):
    def to_embed(self, data: UserModerate | list[UserModerate], ctx: UserModerateCtx) -> discord.Embed:
        # 單筆或取列表第一筆都用同一個 embed
        item = data[0] if isinstance(data, list) else data
        warning_type = ctx.Jsondb.get_tw(item.moderate_type, "warning_type")
        return discord.Embed(
            title=f"<@{item.discord_id}> 的警告單",
            description=f"類型: {warning_type}\n原因: {item.reason}",
            color=0xC4E9FF,
        )

    def to_embeds(self, data: UserModerate | list[UserModerate], ctx: UserModerateCtx) -> list[discord.Embed]:
        items = data if isinstance(data, list) else [data]
        embed = discord.Embed(title="⚠️ 警告紀錄列表", color=0xFF0000)
        embed.description = "\n".join(f"- {m.warning_id}: {m.reason}" for m in items)
        return [embed]


@EmbedFactory.register_decorator(BackupRole)
class BackupRoleTransformer(BaseTransformer[BackupRole, EmptyContext]):
    def to_embed(self, data: BackupRole | list[BackupRole], ctx: EmptyContext) -> discord.Embed:
        item = data[0] if isinstance(data, list) else data
        return discord.Embed(
            title="備份身分組",
            description=f"<@&{item.role_id}>",
            color=0xA8D8EA,
        )

    def to_embeds(self, data: BackupRole | list[BackupRole], ctx: EmptyContext) -> list[discord.Embed]:
        items = data if isinstance(data, list) else [data]
        return [discord.Embed(title="備份身分組", description=f"<@&{r.role_id}>", color=0xA8D8EA) for r in items]
