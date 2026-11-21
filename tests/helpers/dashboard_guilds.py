"""後台伺服器權限測試共用：Discord 權限位元、`g()` 與 `discord` fixture（conftest 以 `discord_env` 提供）。

`discord.guilds` 是 bot 成員快取裡這位使用者的資料，各檔自己的假 bot 只要提供 get_guild，權限由正式的 `_member_perms` 依這份資料判斷。"""

from __future__ import annotations

import pytest

from starServer.dashboard import guilds
from tests.helpers.dashboard_setup import (  # noqa: F401  其他測試檔從這裡 import
    ADMIN,
    BAN,
    KICK,
    MANAGE_CHANNELS,
    MANAGE_GUILD,
    MANAGE_MESSAGES,
    MANAGE_ROLES,
    MODERATE,
    bot_guild,
    g,
    member,
)


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
