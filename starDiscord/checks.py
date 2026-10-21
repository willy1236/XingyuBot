import functools

import discord
from discord.ext import commands

from starlib import sqldb
from starlib.database import PrivilegeLevel
from starlib.database.postgresql.cache import _MISSING, TTLCache
from starlib.database.postgresql.models import HappycampVIP
from starlib.identity import BotIdentity, IdentityUnavailable, privilege_of, resolve_identity

SUSPENDED_MESSAGE = "你的析域帳號已停權，無法使用此功能"

_vip_cache: TTLCache[HappycampVIP | None] = TTLCache(ttl=300)


def _get_vip_cached(user_id: int) -> HappycampVIP | None:
    """取得 VIP 資料，優先從快取讀取。"""
    result = _vip_cache.get(user_id)
    if result is _MISSING:
        result = sqldb.get_vip(user_id)
        _vip_cache.set(user_id, result)
    return result  # type: ignore[return-value]


class PrivilegeError(commands.CheckFailure, discord.ApplicationCommandError):
    """權限等級不足。繼承 commands.CheckFailure 才會被 check_any 當成「這項沒過」而繼續看下一項，
    同時繼承 ApplicationCommandError，單獨使用時 error.py 會直接顯示訊息。"""


def has_privilege_level(privilege: PrivilegeLevel):
    """權限等級由 auth server 的身分組決定，對照表見設定 PRIVILEGE_ROLES。可直接放進 commands.check_any。"""

    async def predicate(ctx: discord.ApplicationContext):
        try:
            # create=False：只是檢查權限，不替沒用過 bot 的人發臨時 ID
            identity = await resolve_identity(ctx.author.id, create=False)
        except IdentityUnavailable:
            identity = None
        if privilege_of(identity) >= privilege:
            return True
        raise PrivilegeError(f"權限錯誤：你沒有權限使用此指令，所需權限等級：{privilege.name}（{privilege.value}）")

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

class IdentityContext(discord.ApplicationContext):
    """
    經過 with_identity() 的指令會多一個屬性 identity，代表該 Discord 帳號對應的使用者 ID
    指令的 ctx 參數類型應設定為 IdentityContext，以便在指令內使用 ctx.identity
    """

    identity: BotIdentity


def with_identity():
    """取得使用者 ID 後才進入指令；沒註冊的人拿到臨時 ID，auth server 連不上又沒有紀錄時回覆稍後再試，被停權的人直接擋下"""

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(cog, ctx: discord.ApplicationContext, *args, **kwargs):
            try:
                ctx.identity = await resolve_identity(ctx.author.id)
            except IdentityUnavailable:
                await ctx.respond("身分服務暫時無法連線，請稍後再試", ephemeral=True)
                return
            if ctx.identity.suspended:
                await ctx.respond(SUSPENDED_MESSAGE, ephemeral=True)
                return
            return await func(cog, ctx, *args, **kwargs)

        return wrapper

    return decorator
