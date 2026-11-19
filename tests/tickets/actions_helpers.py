"""客服單操作測試共用：假伺服器、成員、客服單頻道與權限覆寫。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import discord

from starlib.tickets import overwrite_key

GUILD_ID = 8_800_000_000_004_001
LOBBY = 8_800_000_000_004_011
CATEGORY = 8_800_000_000_004_021


TICKET, TICKET_2 = 8_800_000_000_004_031, 8_800_000_000_004_032


CONTROL = 8_800_000_000_004_041


ROLE_MANAGER, ROLE_OTHER, ROLE_CATEGORY = 8_800_000_000_004_051, 8_800_000_000_004_052, 8_800_000_000_004_053


CREATOR, MANAGER, ADMIN, STRANGER, UNCACHED = (
    8_800_000_000_004_061,
    8_800_000_000_004_062,
    8_800_000_000_004_063,
    8_800_000_000_004_064,
    8_800_000_000_004_065,
)


BOT = 8_800_000_000_004_099
CREATED = datetime(2026, 1, 1, tzinfo=UTC)
OPEN = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
HIDDEN = discord.PermissionOverwrite(view_channel=False)


def http_error(cls=discord.HTTPException, status=500):
    return cls(SimpleNamespace(status=status, reason="boom"), "boom")


class RawOverwrite:
    """`channel._overwrites` 的元素（py-cord 的 `_Overwrites`）。"""

    def __init__(self, tid: int, kind: int, overwrite: discord.PermissionOverwrite):
        allow, deny = overwrite.pair()
        self.id, self.type, self.allow, self.deny = tid, kind, allow.value, deny.value

    def is_role(self):
        return self.type == 0

    def is_member(self):
        return self.type == 1


class FakeRole:
    def __init__(self, rid: int):
        self.id = rid


class FakeMember:
    def __init__(self, uid: int, roles=(), manage_channels=False):
        self.id = uid
        self.name = f"user{uid}"
        self.mention = f"<@{uid}>"
        self.roles = [FakeRole(r) for r in roles]
        self.guild_permissions = SimpleNamespace(manage_channels=manage_channels)


class FakeMessage:
    def __init__(self, mid: int, custom_ids=()):
        self.id = mid
        self.components = [SimpleNamespace(children=[SimpleNamespace(custom_id=c) for c in custom_ids])]
        self.edits: list[dict] = []

    async def edit(self, **kwargs):
        self.edits.append(kwargs)


class FakeCategory:
    type = discord.ChannelType.category

    def __init__(self, guild):
        self.guild = guild
        self.id = CATEGORY
        self._overwrites = [
            RawOverwrite(ROLE_CATEGORY, 0, discord.PermissionOverwrite(view_channel=True, send_messages=False)),
            RawOverwrite(ROLE_OTHER, 0, discord.PermissionOverwrite(send_messages=True)),
        ]


class FakeTicketChannel:
    """py-cord 的行為：`edit`、`set_permissions` 只改 Discord 上的狀態（`truth`），不更新本地快取 `_overwrites`；
    快取要等 gateway 事件（`sync()`）。`guild.fetch_channel` 回一份帶最新覆寫的新物件。"""

    type = discord.ChannelType.text

    def __init__(self, guild, cid: int, overwrites: dict[tuple[str, int], discord.PermissionOverwrite]):
        self.guild = guild
        self.id = cid
        self.mention = f"<#{cid}>"
        self.category = guild.category
        self.set_overwrites(overwrites)
        self.edits: list[tuple[dict, str | None]] = []
        self.sent: list[str] = []
        self.deleted_reason: str | None = None
        self.messages: dict[int, FakeMessage] = {CONTROL: FakeMessage(CONTROL)}
        self.fail_edit: Exception | None = None
        self.fail_delete: Exception | None = None

    def set_overwrites(self, overwrites):
        """設定 Discord 上的覆寫並同步快取（測試的前置狀態）。"""
        self.truth = {
            "ows": [RawOverwrite(tid, 0 if kind == "role" else 1, o) for (kind, tid), o in overwrites.items()]
        }
        self.sync()

    def sync(self):
        """模擬 gateway 的 CHANNEL_UPDATE 到達：快取追上 Discord 上的狀態。"""
        self._overwrites = list(self.truth["ows"])

    def fetched(self):
        copy = object.__new__(FakeTicketChannel)
        copy.__dict__.update(self.__dict__)
        copy._overwrites = list(self.truth["ows"])
        return copy

    def state(self) -> dict[str, discord.PermissionOverwrite]:
        """Discord 上目前的覆寫：鍵 → 覆寫"""
        return {
            overwrite_key("role" if o.is_role() else "member", o.id): discord.PermissionOverwrite.from_pair(
                discord.Permissions(o.allow), discord.Permissions(o.deny)
            )
            for o in self.truth["ows"]
        }

    async def set_permissions(self, target, *, overwrite=None, reason=None):
        kind = 0 if target.id in self.guild.roles else 1
        rest = [o for o in self.truth["ows"] if o.id != target.id]
        self.truth["ows"] = rest if overwrite is None else [*rest, RawOverwrite(target.id, kind, overwrite)]

    def send_of(self, key: str):
        return self.state()[key].send_messages

    async def edit(self, *, overwrites, reason=None):
        # 讓並行的流程有機會交錯
        for _ in range(3):
            await asyncio.sleep(0)
        if self.fail_edit is not None:
            raise self.fail_edit
        self.edits.append((overwrites, reason))
        self.truth["ows"] = [RawOverwrite(t.id, 0 if t.id in self.guild.roles else 1, o) for t, o in overwrites.items()]

    async def send(self, text, **kwargs):
        self.sent.append(text)

    def get_partial_message(self, mid):
        return self.messages.setdefault(mid, FakeMessage(mid))

    async def fetch_message(self, mid):
        if mid not in self.messages:
            raise http_error(discord.NotFound, 404)
        return self.messages[mid]

    async def delete(self, *, reason=None):
        if self.fail_delete is not None:
            raise self.fail_delete
        self.deleted_reason = reason
        self.guild.channels.pop(self.id, None)


class FakeGuild:
    def __init__(self):
        self.id = GUILD_ID
        self.unavailable = False
        self.roles = {r: FakeRole(r) for r in (GUILD_ID, ROLE_MANAGER, ROLE_OTHER, ROLE_CATEGORY)}
        self.members = {
            uid: FakeMember(uid)
            for uid in (CREATOR, MANAGER, ADMIN, STRANGER, BOT)  # UNCACHED 不在成員快取
        }
        self.me = self.members[BOT]
        self.category = FakeCategory(self)
        self.channels: dict[int, object] = {CATEGORY: self.category}
        self.fail_fetch: Exception | None = None

    def get_channel(self, cid):
        return self.channels.get(cid)

    async def fetch_channel(self, cid):
        if self.fail_fetch is not None:
            raise self.fail_fetch
        channel = self.channels.get(cid)
        if not isinstance(channel, FakeTicketChannel):
            raise http_error(discord.NotFound, 404)
        return channel.fetched()

    def get_role(self, rid):
        return self.roles.get(rid)

    def get_member(self, uid):
        return self.members.get(uid)


def ticket_overwrites(bot=True, extra=None) -> dict:
    """P-03 開單後的覆寫：@everyone 看不到，分類覆寫的身分組、建立者、管理身分組、bot 能發言。"""
    ows = {
        ("role", GUILD_ID): HIDDEN,
        ("role", ROLE_CATEGORY): discord.PermissionOverwrite(view_channel=True),
        ("role", ROLE_MANAGER): OPEN,
        ("member", CREATOR): OPEN,
        ("member", UNCACHED): discord.PermissionOverwrite(view_channel=True, send_messages=None),
    }
    if bot:
        ows[("member", BOT)] = OPEN
    ows.update(extra or {})
    return ows


def custom_ids(view: discord.ui.View) -> list[str]:
    return [item.custom_id for item in view.children]  # pyright: ignore[reportAttributeAccessIssue]
