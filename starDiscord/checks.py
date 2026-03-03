import functools

import discord
from discord.ext import commands

from starlib import sqldb
from starlib.database import PrivilegeLevel
from starlib.database.postgresql.cache import _MISSING, TTLCache
from starlib.database.postgresql.models import CloudUser, HappycampVIP

from .uiElement.view import RegisterView

_user_cache: TTLCache[CloudUser] = TTLCache(ttl=300)
_vip_cache: TTLCache[HappycampVIP | None] = TTLCache(ttl=300)


def _get_vip_cached(user_id: int) -> HappycampVIP | None:
    """取得 VIP 資料，優先從快取讀取。"""
    result = _vip_cache.get(user_id)
    if result is _MISSING:
        result = sqldb.get_vip(user_id)
        _vip_cache.set(user_id, result)
    return result  # type: ignore[return-value]


def has_privilege_level(privilege: PrivilegeLevel):
    def predicate(ctx: discord.ApplicationContext):
        cached_user = _user_cache.get(ctx.author.id)
        if cached_user is not _MISSING:
            user_privilege = cached_user.privilege_level  # type: ignore[union-attr]
        else:
            user_privilege = sqldb.get_cloud_user_privilege(ctx.author.id)
        if user_privilege >= privilege:
            return True
        raise discord.ApplicationCommandError(f"權限錯誤：你沒有權限使用此指令，所需權限等級：{privilege.name}（{privilege.value}）")

    return commands.check(predicate)

def has_vip():
    def predicate(ctx: discord.ApplicationContext):
        vip = _get_vip_cached(ctx.author.id)
        if vip:
            return True
        raise discord.ApplicationCommandError("權限錯誤：你沒有權限使用此指令")

    return commands.check(predicate)


def is_vip_admin():
    def predicate(ctx: discord.ApplicationContext):
        vip = _get_vip_cached(ctx.author.id)
        if vip and vip.vip_admin:
            return True
        raise discord.ApplicationCommandError("權限錯誤：你沒有權限使用此指令")

    return commands.check(predicate)

class RegisteredContext(discord.ApplicationContext):
    """
    如果用戶已註冊，則此互動對象會有一個額外的屬性 cuser，代表該用戶的 CloudUser 資料
    指令的ctx參數類型應設定為 RegisteredContext，以便在指令內使用 ctx.cuser 取得用戶資料
    """

    cuser: CloudUser


def ensure_registered():
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(cog, ctx: discord.ApplicationContext, *args, **kwargs):
            user = _user_cache.get(ctx.author.id)
            if user is _MISSING:
                user = sqldb.get_cloud_user_by_discord(ctx.author.id)
                if user:
                    # 只快取已註冊用戶；未註冊者不快取，確保註冊後立即生效
                    _user_cache.set(ctx.author.id, user)

            if user:
                # 已註冊，執行原本的指令函式
                ctx.cuser = user  # 將用戶資料附加到互動對象上，供指令內使用
                return await func(cog, ctx, *args, **kwargs)
            else:
                # 未註冊，發送條款按鈕
                view = RegisterView()
                embed = discord.Embed(title="📝 註冊帳號", description="歡迎使用本服務！在開始之前，請先建立新帳號或綁定原有帳號", color=discord.Color.blue())
                await ctx.respond(embed=embed, view=view, ephemeral=True)
                return  # 中斷執行，不進入原本的指令內容

        return wrapper

    return decorator
