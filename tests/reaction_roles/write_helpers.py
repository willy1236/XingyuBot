"""後台反應身分組寫入測試共用：假 Discord 物件、假 repository、`client` fixture 與 `seed()`。"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import discord
import pytest
from fastapi.testclient import TestClient

from starlib import sclient
from starlib.message_content import MessageContent, to_json
from starServer.dashboard import reaction_roles
from tests.helpers.dashboard_auth import USER_ID, make_app, make_session
from tests.helpers.dashboard_guilds import MANAGE_ROLES, g
from tests.helpers.dashboard_notifies import GUILD_ID
from tests.reaction_roles.dashboard_helpers import (
    BOT_TOP,
    EVERYONE,
    ROLE_ABOVE,
    ROLE_MANAGED,
    ROLE_OK,
    FakeChannel,
)

URL = f"/dashboard/guilds/{GUILD_ID}/reaction-roles"
ACTOR_ID = int(USER_ID)
OWNER_ID = 42
ROLE_HIGH = 3004  # 低於 bot、不低於操作者
ROLE_ADMIN = 3005  # 低於操作者、帶 Administrator
ROLE_B = 3006
EMOJI_OK = "<:ok:700000000000001>"
EMOJI_GONE = "<:gone:700000000000002>"
ACTOR_TOP = 8
EXTRA_ROLE_BASE = 4000


def http_error(status: int = 500) -> discord.HTTPException:
    return discord.HTTPException(SimpleNamespace(status=status, reason="boom"), "boom")


class FakeRole:
    def __init__(self, rid: int, name: str, position: int, managed: bool = False, **permissions):
        self.id = rid
        self.name = name
        self.position = position
        self.managed = managed
        self.color = SimpleNamespace(value=0)
        self.permissions = SimpleNamespace(**permissions)

    def is_default(self) -> bool:
        return self.id == EVERYONE

    def __ge__(self, other: FakeRole) -> bool:
        return self.position >= other.position


class FakeMessage:
    def __init__(self, mid: int, content: str = "", embeds=(), attachments=(), author_id: int = 1, components=()):
        self.id = mid
        self.author = SimpleNamespace(id=author_id)  # bot 的 id 是 1（FakeGuild.me）
        self.components = list(components)
        self.created_at = datetime(2026, 11, 11, tzinfo=UTC) + timedelta(minutes=mid)
        self.content = content
        self.embeds = list(embeds)
        self.attachments = list(attachments)
        self.edits: list[dict] = []
        self.deleted = False
        self.fail_edit = False

    @property
    def jump_url(self) -> str:
        return f"https://discord.com/channels/{GUILD_ID}/501/{self.id}"

    async def edit(self, **kwargs):
        if self.fail_edit:
            raise http_error()
        self.edits.append(kwargs)
        if "content" in kwargs:
            self.content = kwargs["content"] or ""
        if "embeds" in kwargs:
            self.embeds = list(kwargs["embeds"])

    async def delete(self):
        self.deleted = True


class FakeTextChannel(FakeChannel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.category = SimpleNamespace(position=0, name="分類")
        self.sent: list[FakeMessage] = []
        self.send_kwargs: list[dict] = []
        self.fail_send = False
        self.fail_edit_new = False
        self._next = 9000

    async def history(self, limit: int = 100):
        for mid in sorted(self.messages, reverse=True)[:limit]:
            yield self.messages[mid]

    async def send(self, **kwargs):
        if self.fail_send:
            raise http_error(403)
        self._next += 1
        message = FakeMessage(self._next, kwargs.get("content") or "", kwargs.get("embeds") or ())
        message.fail_edit = self.fail_edit_new
        self.send_kwargs.append(kwargs)
        self.sent.append(message)
        self.messages[message.id] = message  # pyright: ignore[reportArgumentType]
        return message


class FakeEmoji:
    id = 700000000000001
    name = "ok"
    animated = False

    def __str__(self) -> str:
        return EMOJI_OK


class FakeGuild:
    def __init__(self):
        self.id = GUILD_ID
        self.unavailable = False
        self.owner_id = OWNER_ID
        self.me = SimpleNamespace(
            id=1, top_role=FakeRole(1, "bot", BOT_TOP), guild_permissions=SimpleNamespace(manage_roles=True)
        )
        self.role_map = {
            ROLE_OK: FakeRole(ROLE_OK, "活動", 5),
            ROLE_B: FakeRole(ROLE_B, "遊戲", 6),
            ROLE_ADMIN: FakeRole(ROLE_ADMIN, "管理員們", 4, administrator=True, manage_roles=True),
            ROLE_HIGH: FakeRole(ROLE_HIGH, "幹部", 9),
            ROLE_ABOVE: FakeRole(ROLE_ABOVE, "管理", BOT_TOP),
            ROLE_MANAGED: FakeRole(ROLE_MANAGED, "整合", 2, managed=True),
            EVERYONE: FakeRole(EVERYONE, "@everyone", 0),
        }
        for i in range(30):
            self.role_map[EXTRA_ROLE_BASE + i] = FakeRole(EXTRA_ROLE_BASE + i, f"額外{i}", 1)
        self.actor = SimpleNamespace(id=ACTOR_ID, top_role=FakeRole(2, "操作者", ACTOR_TOP))
        self.channel = FakeTextChannel(501, "身分組", position=0, category_position=0)
        self.other_channel = FakeTextChannel(502, "閒聊", position=1, category_position=0)
        self.text_channels = [self.channel, self.other_channel]
        self.emojis = [FakeEmoji()]

    @property
    def roles(self):
        return list(self.role_map.values())

    def get_channel(self, cid: int):
        return {c.id: c for c in self.text_channels}.get(cid)

    def get_role(self, rid: int):
        return self.role_map.get(rid)

    def get_member(self, uid: int):
        return self.actor if uid == ACTOR_ID else None

    def get_emoji(self, eid: int):
        return SimpleNamespace(id=eid) if any(e.id == eid for e in self.emojis) else None


class FakeBot:
    def __init__(self, guild: FakeGuild):
        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        pool = ThreadPoolExecutor(max_workers=1)
        self._guild = guild
        self.views: list[tuple[int, discord.ui.View]] = []
        self.is_ready = lambda: True
        self.submit = lambda coro: pool.submit(asyncio.run, coro)

    def get_guild(self, gid: int):
        return self._guild if gid == GUILD_ID else None

    def add_view(self, view, message_id=None):
        self.views.append((message_id, view))


class FakeRepo:
    def __init__(self):
        self.messages: dict[int, dict] = {}
        self.fail_replace = False
        self.replace_calls = 0

    def get_reaction_role_snapshot(self, message_id: int):
        m = self.messages.get(message_id)
        return None if m is None else json.loads(json.dumps(m))

    def list_guild_reaction_roles(self, guild_id: int):
        return [
            (
                SimpleNamespace(channel_id=m["channel_id"], message_id=mid),
                [
                    SimpleNamespace(
                        role_id=b["role_id"], title=b["title"], emoji=b["emoji"], style=b["style"], position=i
                    )
                    for i, b in enumerate(m["buttons"])
                ],
            )
            for mid, m in self.messages.items()
            if m["guild_id"] == guild_id
        ]

    def replace_reaction_role_message(self, guild_id, channel_id, message_id, content_json, options):
        self.replace_calls += 1
        if self.fail_replace:
            raise RuntimeError("db down")
        old = self.messages.get(message_id)
        if content_json is None and old is not None:
            content_json = old["content_json"]
        self.messages[message_id] = {
            "guild_id": guild_id,
            "channel_id": channel_id,
            "content_json": content_json,
            "buttons": [{"role_id": o.role_id, "title": o.title, "emoji": o.emoji, "style": o.style} for o in options],
        }


@pytest.fixture
def client(discord_env, dashboard_env, repo, monkeypatch) -> TestClient:
    make_session(repo)
    discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_ROLES)]
    fake_repo = FakeRepo()
    monkeypatch.setattr(reaction_roles, "sqldb", fake_repo)
    guild = FakeGuild()
    bot = FakeBot(guild)
    monkeypatch.setattr(sclient, "bot", bot)
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
    c.cookies.set("dashboard_session", "sid")
    c.repo = fake_repo  # pyright: ignore[reportAttributeAccessIssue]
    c.guild = guild  # pyright: ignore[reportAttributeAccessIssue]
    c.bot = bot  # pyright: ignore[reportAttributeAccessIssue]
    c.discord_env = discord_env  # pyright: ignore[reportAttributeAccessIssue]
    return c


def btn(role: int, title: str = "按鈕", emoji: str | None = None, style: int | None = 1) -> dict:
    return {"role_id": str(role), "title": title, "emoji": emoji, "style": style}


TEXT = {"content": "請選身分組", "embed": None}


def seed(
    client, mid: int, buttons: list[dict], *, content: MessageContent | None = None, message: FakeMessage | None = None
) -> FakeMessage:
    """放一則已存在的反應身分組訊息（Discord 與假 repository 各一份）；content 為 None 時 content_json 留空。"""
    client.repo.messages[mid] = {
        "guild_id": GUILD_ID,
        "channel_id": 501,
        "content_json": to_json(content) if content else None,
        "buttons": [
            {"role_id": int(b["role_id"]), "title": b["title"], "emoji": b["emoji"], "style": b["style"]}
            for b in buttons
        ],
    }
    message = message or FakeMessage(mid, content.content if content else "舊內容")
    client.guild.channel.messages[mid] = message
    return message


def original(client, mid: int) -> dict:
    d = client.get(f"{URL}/{mid}").json()
    return {
        "content_json": d["content_json"],
        "buttons": [{k: b[k] for k in ("role_id", "title", "emoji", "style")} for b in d["buttons"]],
    }


def fields(response) -> list[tuple[str, str]]:
    return [(f["path"], f["reason"]) for f in response.json()["fields"]]
