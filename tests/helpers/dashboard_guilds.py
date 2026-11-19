"""後台伺服器權限測試共用：Discord 權限位元、`g()` 與 `discord` fixture（conftest 以 `discord_env` 提供）。

`discord.guilds` 是 bot 成員快取裡這位使用者的資料，各檔自己的假 bot 只要提供 get_guild，權限由正式的 `_member_perms` 依這份資料判斷。"""

from __future__ import annotations

from types import SimpleNamespace

import discord as dpy
import pytest

from starServer.dashboard import guilds

ADMIN = 0x8
MANAGE_CHANNELS = 0x10
MANAGE_GUILD = 0x20
KICK = 0x2
BAN = 0x4
MANAGE_MESSAGES = 0x2000
MANAGE_ROLES = 0x10000000
MODERATE = 0x10000000000


def g(gid: str, name: str, permissions: int = 0, owner: bool = False) -> dict:
    """使用者在伺服器 gid 的成員資料：permissions 是 guild_permissions 的 bits，owner 表示是伺服器擁有者。"""
    return {"id": gid, "name": name, "owner": owner, "permissions": permissions}


class FakeDiscord:
    def __init__(self):
        # 使用者是成員的伺服器；不在這裡的伺服器視為不是成員
        self.guilds: list[dict] = []


@pytest.fixture
def discord(monkeypatch, dashboard_env, repo) -> FakeDiscord:
    fake = FakeDiscord()
    real_member_perms = guilds._member_perms

    def member_perms(guild, user_id: int) -> guilds.GuildPerms:
        """把各檔自己的假伺服器換成帶有 fake.guilds 成員資料的伺服器，再交給正式的判斷。"""
        entry = next((e for e in fake.guilds if e["id"] == str(guild.id)), None)
        members = [member(user_id, entry["permissions"])] if entry else []
        owner_id = user_id if entry and entry["owner"] else 1
        return real_member_perms(bot_guild(guild.id, "guild", members, owner_id=owner_id), user_id)

    monkeypatch.setattr(guilds, "_member_perms", member_perms)
    return fake


def member(user_id: str | int, permissions: int = 0):
    return SimpleNamespace(id=int(user_id), guild_permissions=dpy.Permissions(permissions))


def bot_guild(gid: int, name: str, members=(), owner_id: int = 1, icon: str | None = None):
    by_id = {m.id: m for m in members}
    return SimpleNamespace(
        id=gid,
        name=name,
        owner_id=owner_id,
        icon=SimpleNamespace(url=icon) if icon else None,
        get_member=by_id.get,
    )
