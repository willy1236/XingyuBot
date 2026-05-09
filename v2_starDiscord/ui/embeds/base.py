# base.py  ─────────────────────────────────────────────────────────────────
# Runtime 層：保持動態 registry，不依賴任何靜態型別魔法。
# 靜態型別由 embeds.pyi（codegen 自動產生）提供，IDE 讀 .pyi，不執行它。
# ────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import discord

# ── Context ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EmptyContext:
    """不需要任何外部依賴時使用的預設 Context。"""


# ── BaseTransformer ───────────────────────────────────────────────────────────


class BaseTransformer[T_Model, T_Ctx]:
    """
    所有 Transformer 的基底。
    泛型參數：[資料模型, 專屬 Context]

    - to_embed  ：接受 single 或 list，回傳 discord.Embed
    - to_embeds ：接受 single 或 list，回傳 list[discord.Embed]

    子類別只需實作有用到的方法，未實作的呼叫時會拋 NotImplementedError。

    子類別範例：
        class UserModerateTransformer(BaseTransformer[UserModerate, UserModerateCtx]):
            def to_embed(
                self, data: UserModerate | list[UserModerate], ctx: UserModerateCtx
            ) -> discord.Embed: ...
            def to_embeds(
                self, data: UserModerate | list[UserModerate], ctx: UserModerateCtx
            ) -> list[discord.Embed]: ...
    """

    def to_embed(self, data: T_Model | list[T_Model], ctx: T_Ctx) -> discord.Embed:
        raise NotImplementedError

    def to_embeds(self, data: T_Model | list[T_Model], ctx: T_Ctx) -> list[discord.Embed]:
        raise NotImplementedError


# ── EmbedFactory ─────────────────────────────────────────────────────────────

class BaseBotEmbed:
    @staticmethod
    def bot(bot: discord.Bot, title: str | None = None, description: str | None = None, url: str | None = None):
        """機器人 格式"""
        assert bot.user is not None, "Bot user must be set before creating an embed."
        embed = discord.Embed(title=title, description=description, color=0xC4E9FF, url=url)
        embed.set_author(name=bot.user.name, icon_url=bot.user.display_avatar.url)
        return embed

    @staticmethod
    def user(user: discord.User, title: str | None = None, description: str | None = None, url: str | None = None):
        """使用者 格式"""
        embed = discord.Embed(title=title, description=description, color=0x00FFFF, url=url)
        embed.set_author(name=user.name, icon_url=user.display_avatar.url)
        return embed

    @staticmethod
    def simple(title: str | None = None, description: str | None = None, url: str | None = None):
        """簡易:不帶作者"""
        embed = discord.Embed(title=title, description=description, color=0xC4E9FF, url=url)
        return embed

    @staticmethod
    def general(
        name: str | None = None,
        icon_url: str | None = None,
        url: str | None = None,
        title: str | None = None,
        description: str | None = None,
        title_url: str | None = None,
    ):
        """普通:自訂作者"""
        embed = discord.Embed(title=title, description=description, color=0xC4E9FF, url=title_url)
        embed.set_author(name=name, icon_url=icon_url, url=url)
        return embed

    @staticmethod
    def deprecated():
        """棄用:展示棄用訊息"""
        embed = discord.Embed(title="此功能目前為棄用狀態", description="此功能目前不開放使用，請洽機器人管理員或支援伺服器", color=0xC4E9FF)
        return embed

    @staticmethod
    def rpg(title: str | None = None, description: str | None = None):
        """RPG系統 格式"""
        embed = discord.Embed(title=title, description=description, color=0xC4E9FF)
        embed.set_footer(text="RPG系統 | 開發時期所有東西皆有可能重置")
        return embed

    @staticmethod
    def info(title: str | None = None, description: str | None = None, url: str | None = None):
        """一般資訊 格式"""
        embed = discord.Embed(title=title, description=description, color=0xC4E9FF, url=url)
        return embed

    @staticmethod
    def simple_warn_sheet(
        warn_user: discord.User | discord.Member,
        moderate_user: discord.abc.User | discord.Member | discord.ClientUser,
        create_at: datetime | None = None,
        last: timedelta = timedelta(seconds=15),
        reason: str = "未提供原因",
        title: str = "已被禁言",
    ):
        """簡易警告表格"""
        if create_at is None:
            create_at = datetime.now()
        timestamp = create_at + last
        embed = discord.Embed(description=f"{warn_user.mention}：{reason}", color=0xC4E9FF)
        embed.set_author(name=f"{warn_user.name} {title}", icon_url=warn_user.display_avatar.url)
        embed.add_field(name="執行人員", value=moderate_user.mention)
        embed.add_field(name="結束時間", value=f"{discord.utils.format_dt(timestamp, style='t')}（{last.total_seconds():.0f}s）")
        embed.timestamp = create_at
        return embed


class BotEmbed(BaseBotEmbed):
    """
    全專案唯一的萬用入口，所有方法皆為 classmethod。

    呼叫方式（靜態型別由 embeds.pyi 保證）：
        EmbedFactory.to_embed(user_moderate, UserModerateCtx(Jsondb=db))
        EmbedFactory.to_embeds(user_moderate_list, UserModerateCtx(Jsondb=db))
    """

    _registry: dict[type, BaseTransformer[Any, Any]] = {}

    @classmethod
    def register[M, C](
        cls,
        model_class: type[M],
        transformer: BaseTransformer[M, C],
    ) -> None:
        cls._registry[model_class] = transformer

    @classmethod
    def register_decorator[M, C](cls, model_class: type[M]):
        """
        class decorator 用法：

            @EmbedFactory.register_decorator(UserModerate)
            class UserModerateTransformer(BaseTransformer[UserModerate, UserModerateCtx]):
                ...
        """

        def decorator(transformer_cls: type[BaseTransformer[M, C]]) -> type[BaseTransformer[M, C]]:
            cls.register(model_class, transformer_cls())
            return transformer_cls

        return decorator

    @classmethod
    def _get_transformer(cls, data: Any) -> BaseTransformer[Any, Any]:
        model_type = type(data[0]) if isinstance(data, list) else type(data)
        transformer = cls._registry.get(model_type)
        if not transformer:
            raise ValueError(f"未註冊 Transformer: {model_type}")
        return transformer

    @classmethod
    def to_embed(cls, data: Any, ctx: Any = EmptyContext()) -> discord.Embed:
        """回傳單一 discord.Embed。"""
        return cls._get_transformer(data).to_embed(data, ctx)

    @classmethod
    def to_embeds(cls, data: Any, ctx: Any = EmptyContext()) -> list[discord.Embed]:
        """回傳 list[discord.Embed]。"""
        return cls._get_transformer(data).to_embeds(data, ctx)
