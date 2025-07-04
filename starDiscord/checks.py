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
