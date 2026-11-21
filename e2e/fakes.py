"""假的 Discord：bot 與一個伺服器。介面只做到後台第一批情境用得到的部分，其他呼叫會以 AttributeError 在情境裡露出來。"""

from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

import discord

from tests.helpers.dashboard_setup import ADMIN, USER_ID

GUILD_ID = 9100000000000001
GUILD_NAME = "E2E 測試伺服器"
USER = int(USER_ID)
FRIEND = 9100000000000102
STRANGER = 9100000000000103
BOT_ID = 9100000000000100

CHANNEL_GENERAL = 9100000000000201
CHANNEL_ANNOUNCE = 9100000000000202
ROLE_MEMBER = 9100000000000301

EVERYTHING = discord.Permissions.all()


class FakeMember:
    def __init__(self, uid: int, name: str, *, bot: bool = False, permissions: int = 0):
        self.id = uid
        self.name = name
        self.display_name = name
        self.is_bot = bot
        self.guild_permissions = discord.Permissions(permissions)
        self.display_avatar = SimpleNamespace(url=f"https://cdn.example.test/{uid}.png")


class FakeChannel:
    def __init__(self, cid: int, name: str, type=discord.ChannelType.text, position: int = 0):
        self.id, self.name, self.type, self.position = cid, name, type, position
        self.category = None
        self.sent: list[dict] = []

    def permissions_for(self, member):
        return EVERYTHING

    async def send(self, **kwargs):
        self.sent.append(kwargs)
        return SimpleNamespace(id=9100000000009000 + len(self.sent), delete=_noop)


async def _noop():
    return None


def _role(rid: int, name: str, position: int, *, default: bool = False):
    return SimpleNamespace(
        id=rid,
        name=name,
        position=position,
        managed=False,
        mentionable=True,
        color=SimpleNamespace(value=0x3366CC),
        is_default=lambda: default,
        mention=f"<@&{rid}>",
    )


class FakeGuild:
    """使用者（USER）是管理員；FRIEND 在語音排行上，STRANGER 不在伺服器內。"""

    def __init__(self):
        self.id = GUILD_ID
        self.name = GUILD_NAME
        self.icon = None
        self.owner_id = 1
        self.unavailable = False
        self.me = FakeMember(BOT_ID, "星羽", bot=True, permissions=ADMIN)
        self.members = {
            m.id: m for m in (FakeMember(USER, "Some One", permissions=ADMIN), FakeMember(FRIEND, "Friend"))
        }
        self.channels = {
            c.id: c
            for c in (
                FakeChannel(CHANNEL_GENERAL, "一般", position=1),
                FakeChannel(CHANNEL_ANNOUNCE, "公告", discord.ChannelType.news, position=2),
            )
        }
        self.roles = [_role(GUILD_ID, "@everyone", 0, default=True), _role(ROLE_MEMBER, "成員", 1)]

    @property
    def text_channels(self):
        return list(self.channels.values())

    def get_member(self, uid: int):
        return self.members.get(uid)

    def get_channel(self, cid: int):
        return self.channels.get(cid)

    def get_channel_or_thread(self, cid: int):
        return self.channels.get(cid)

    def get_role(self, rid: int):
        return next((r for r in self.roles if r.id == rid), None)


class FakeBot:
    """`submit` 在自己的 event loop 執行緒跑 coroutine，行為同 `starDiscord/bot.py` 的 DiscordBot.submit。"""

    def __init__(self, *guilds: FakeGuild):
        self.guilds = list(guilds)
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self.loop.run_forever, name="e2e-fake-bot", daemon=True)
        self._thread.start()

    def is_ready(self) -> bool:
        return True

    def get_guild(self, gid: int):
        return next((g for g in self.guilds if g.id == gid), None)

    def submit(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    async def is_owner(self, user) -> bool:
        return False

    def stop(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout=5)
