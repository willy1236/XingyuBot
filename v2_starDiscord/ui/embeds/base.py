# base.py  ─────────────────────────────────────────────────────────────────
# Runtime 層：保持動態 registry，不依賴任何靜態型別魔法。
# 靜態型別由 embeds.pyi（codegen 自動產生）提供，IDE 讀 .pyi，不執行它。
# ────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

from dataclasses import dataclass
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


class EmbedFactory:
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
