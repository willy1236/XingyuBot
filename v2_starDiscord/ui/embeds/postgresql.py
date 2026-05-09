# embeds/postgresql.py ───────────────────────────────────────────────────────
from __future__ import annotations

from dataclasses import dataclass

import discord

from v2_starDiscord.bot import DiscordBot
from v2_starlib.database.postgresql.models import (
    BackupCategory,
    BackupChannel,
    BackupMessage,
    BackupRole,
    HappycampApplicationForm,
    UserModerate,
)
from v2_starlib.fileDatabase import JsonDatabase

from .base import BaseTransformer, BotEmbed, EmptyContext

# ── Contexts ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class UserModerateCtx:
    Jsondb: JsonDatabase
    bot: DiscordBot


# ── Transformers ─────────────────────────────────────────────────────────────


@BotEmbed.register_decorator(UserModerate)
class UserModerateTransformer(BaseTransformer[UserModerate, UserModerateCtx]):
    def to_embed(self, data: UserModerate | list[UserModerate], ctx: UserModerateCtx) -> discord.Embed:
        # 單筆或取列表第一筆都用同一個 embed
        item = data[0] if isinstance(data, list) else data
        bot = ctx.bot
        Jsondb = ctx.Jsondb
        if isinstance(data, list):
            user = bot.get_user(item.discord_id)
            embed = BotEmbed.general(
                f"{user.name if user else f'<@{item.discord_id}>'} 的警告單列表（共{len(data)}筆）",
                user.display_avatar.url if user else None,
            )
            for i in data:
                moderate_user = bot.get_user(i.moderate_user)
                guild = bot.get_guild(i.create_guild)
                name = f"編號：{i.warning_id}（{Jsondb.get_tw(i.moderate_type, 'warning_type')}）"
                value = f"{guild.name if guild else i.create_guild}/{moderate_user.mention if moderate_user else f'<@{i.moderate_user}>'}\n{i.reason}\n{i.create_time.strftime('%Y-%m-%d %H:%M:%S')}"
                if i.officially_given and i.guild_only:
                    value += "\n官方認證警告 & 伺服器內警告"
                elif i.officially_given:
                    value += "\n官方認證警告"
                elif i.guild_only:
                    value += "\n伺服器內警告"

                embed.add_field(name=name, value=value)
            return embed
        else:
            user_mention = f"<@{data.discord_id}>"

            moderator_mention = f"<@{data.moderate_user}>"
            warning_type = Jsondb.get_tw(data.moderate_type, "warning_type")
            status_text = (
                f"**編號：{data.warning_id}（{warning_type}）**\n- 被警告用戶：{user_mention}\n- 管理員：<@{data.create_guild}>/{moderator_mention}\n- 原因：{data.reason}\n- 時間：{data.create_time.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            if data.last_time:
                status_text += f"\n- 禁言時長：{data.last_time}"
            if data.officially_given:
                status_text += "\n- 官方認證警告"
            if data.guild_only:
                status_text += "\n- 伺服器內警告"

            embed = discord.Embed(title=f"{user_mention} 的警告單", description=status_text, color=0xC4E9FF)
            return embed

    def to_embeds(self, data: UserModerate | list[UserModerate], ctx: UserModerateCtx) -> list[discord.Embed]:
        items = data if isinstance(data, list) else [data]
        embed = discord.Embed(title="⚠️ 警告紀錄列表", color=0xFF0000)
        embed.description = "\n".join(f"- {m.warning_id}: {m.reason}" for m in items)
        return [embed]


@BotEmbed.register_decorator(BackupRole)
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
