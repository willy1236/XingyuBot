import discord
from discord.ext import commands

from starlib import sqldb
from starlib.types import PrivilegeLevel


def has_privilege_level(privilege: PrivilegeLevel):
    def predicate(ctx: discord.ApplicationContext):
        user_privilege = sqldb.get_cloud_user_privilege(ctx.author.id)
        if user_privilege >= privilege:
            return True
        raise discord.ApplicationCommandError(f"權限錯誤：你沒有權限使用此指令，所需權限等級：{privilege.name}（{privilege.value}）")

    return commands.check(predicate)

def has_vip():
    def predicate(ctx: discord.ApplicationContext):
        vip = sqldb.get_vip(ctx.author.id)
        if vip:
            return True
        raise discord.ApplicationCommandError("權限錯誤：你沒有權限使用此指令")

    return commands.check(predicate)


def is_vip_admin():
    def predicate(ctx: discord.ApplicationContext):
        vip = sqldb.get_vip(ctx.author.id)
        if vip and vip.vip_admin:
            return True
        raise discord.ApplicationCommandError("權限錯誤：你沒有權限使用此指令")

    return commands.check(predicate)
