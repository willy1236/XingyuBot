import random

import discord
from discord.ext import commands


class ChoiceList:
    @staticmethod
    def set(option_name: str):
        return [discord.OptionChoice(name=name_loc.get("en-US", name_loc.get("zh-TW")), value=value, name_localizations=name_loc) for value, name_loc in Jsondb.options[option_name].items()]

    @staticmethod
    def name(cmd_name: str):
        """name_localizations 格式化"""
        return Jsondb.cmd_names[cmd_name]


async def create_only_role_list(text_input: str, ctx):
    """投票系統：建立限制投票身分組清單"""
    only_role_list = []
    for i in text_input.split(","):
        if i.endswith(" "):
            i = i[:-1]
        role = await find.role(ctx, i)
        if role:
            only_role_list.append(role.id)
    return only_role_list


async def create_role_magification_dict(text_input: str, ctx) -> dict[int, int]:
    """投票系統：建立身分組權重列表"""
    role_magnification_dict = {}
    text = text_input.split(",")
    for i in range(0, len(text), 2):
        if text[i].endswith(" "):
            text[i] = text[i][:-1]
        role = await find.role(ctx, text[i])
        if role:
            role_magnification_dict[role.id] = int(text[i + 1])
    return role_magnification_dict


def random_color(max=255):
    if max > 255:
        raise ValueError("max must below 256")
    return (random.randint(0, max), random.randint(0, max), random.randint(0, max))


class find:
    """arg=要檢測的內容(名稱#0000,id,mention...)"""

    @staticmethod
    async def user(ctx, arg: str):
        if arg:
            try:
                member = await commands.MemberConverter().convert(ctx, str(arg))
            except commands.MemberNotFound:
                member = None
        else:
            member = None
        return member

    @staticmethod
    async def channel(ctx, arg: str):
        if arg:
            try:
                channel = await commands.TextChannelConverter().convert(ctx, str(arg))
            except commands.ChannelNotFound:
                channel = None
        else:
            channel = None
        return channel

    @staticmethod
    async def role(ctx, arg: str):
        if arg:
            try:
                role = await commands.RoleConverter().convert(ctx, str(arg))
            except commands.RoleNotFound:
                role = None
        else:
            role = None
        return role

    @staticmethod
    async def user2(ctx, arg: str):
        try:
            user = await commands.UserConverter().convert(ctx, str(arg))
        except commands.UserNotFound:
            user = None
        return user

    @staticmethod
    async def emoji(ctx, arg: str):
        try:
            emoji = await commands.EmojiConverter().convert(ctx, str(arg))
        except commands.EmojiNotFound:
            emoji = None
        return emoji

    @staticmethod
    async def guild(ctx, arg: str):
        try:
            guild = await commands.GuildConverter().convert(ctx, str(arg))
        except commands.GuildNotFound:
            guild = None
        return guild
