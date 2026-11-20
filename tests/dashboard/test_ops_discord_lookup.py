"""營運入口的 Discord ID 查詢（假 bot；權限檢查走真實 PostgreSQL，測完 rollback）。"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from types import SimpleNamespace

import discord
import pytest
from fastapi.testclient import TestClient

from starlib import sclient
from tests.helpers.dashboard_auth import FRONTEND, USER_ID, make_app, make_session

pytestmark = pytest.mark.usefixtures("dashboard_env")

URL = "/dashboard/ops/discord/lookup"
AT = datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)
ME = 999


def http_error(cls: type[discord.HTTPException], status: int) -> discord.HTTPException:
    return cls(SimpleNamespace(status=status, reason="x"), "x")


def fake_role(role_id: int, *, default: bool = False, color: int = 0x3498DB):
    return SimpleNamespace(
        id=role_id,
        name=f"role{role_id}",
        position=3,
        color=discord.Colour(color),
        permissions=discord.Permissions(2**40 + 8),
        is_default=lambda: default,
    )


def fake_guild(guild_id: int, *, members=None, roles=(), chunked: bool = True):
    members = members or {}
    roles = {r.id: r for r in roles}
    roles.setdefault(guild_id, fake_role(guild_id, default=True))
    return SimpleNamespace(
        id=guild_id,
        name=f"g{guild_id}",
        icon=None,
        owner_id=7,
        owner=None,
        member_count=12,
        text_channels=[1, 2],
        voice_channels=[3],
        verification_level=discord.VerificationLevel.medium,
        created_at=AT,
        chunked=chunked,
        get_member=members.get,
        get_role=roles.get,
    )


def fake_member(top_role):
    return SimpleNamespace(
        nick="暱稱",
        top_role=top_role,
        joined_at=AT,
        timed_out=True,
        raw_status="idle",
        activity=SimpleNamespace(name="Minecraft"),
    )


def fake_user(user_id: int, mutual=()):
    return SimpleNamespace(
        id=user_id,
        name="alice",
        global_name="Alice",
        display_avatar=SimpleNamespace(url="https://cdn/a.png"),
        created_at=AT,
        bot=False,
        system=False,
        mutual_guilds=list(mutual),
    )


def fake_message(message_id: int, *, content: str, author_id: int = 5, guild=None, mentions=()):
    return SimpleNamespace(
        id=message_id,
        guild=guild,
        author=SimpleNamespace(
            id=author_id, display_name="作者", display_avatar=SimpleNamespace(url="https://cdn/b.png")
        ),
        content=content,
        mentions=list(mentions),
        created_at=AT,
        jump_url="https://discord.com/channels/1/2/3",
        embeds=[discord.Embed(title="標題")],
        attachments=[],
    )


def fake_channel(channel_id: int, *, guild=None, messages=None, fetch_error=None, messageable: bool = True):
    attrs = dict(
        id=channel_id,
        name=f"c{channel_id}",
        type=discord.ChannelType.text,
        category=SimpleNamespace(id=50, name="類別"),
        guild=guild,
        created_at=AT,
    )
    if messageable:

        async def fetch_message(message_id: int):
            if fetch_error is not None:
                raise fetch_error
            if messages is None or message_id not in messages:
                raise http_error(discord.NotFound, 404)
            return messages[message_id]

        attrs["fetch_message"] = fetch_message
    return SimpleNamespace(**attrs)


@pytest.fixture
def world(monkeypatch):
    """假 bot 的快取；測試往裡面放東西。fetch_user 預設 404，可改成丟指定的例外。"""
    pool = ThreadPoolExecutor(max_workers=1)
    state = SimpleNamespace(
        ready=True,
        guilds=[],
        users={},
        fetched={},
        fetch_error=None,
        channels={},
        intents=discord.Intents.all(),
    )

    async def is_owner(user):
        return user.id == int(USER_ID)

    async def fetch_user(user_id: int):
        if state.fetch_error is not None:
            raise state.fetch_error
        if user_id in state.fetched:
            return state.fetched[user_id]
        raise http_error(discord.NotFound, 404)

    fake = SimpleNamespace(
        is_owner=is_owner,
        is_ready=lambda: state.ready,
        guilds=state.guilds,
        get_guild=lambda i: next((g for g in state.guilds if g.id == i), None),
        get_user=state.users.get,
        fetch_user=fetch_user,
        get_channel=state.channels.get,
        submit=lambda coro: pool.submit(asyncio.run, coro),
        user=SimpleNamespace(id=ME),
    )
    fake.intents = state.intents
    monkeypatch.setattr(sclient, "bot", fake)
    yield state
    pool.shutdown()


@pytest.fixture
def owner(repo, world) -> TestClient:
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
    c.cookies.set("dashboard_session", make_session(repo))
    c.headers["Origin"] = FRONTEND
    return c


def kinds(body) -> list[str]:
    return [m["kind"] for m in body["matches"]]


def test_non_owner_is_forbidden(repo, world, monkeypatch):
    async def nobody(user):
        return False

    monkeypatch.setattr(sclient.bot, "is_owner", nobody)
    c = TestClient(make_app(), base_url="https://testserver")
    c.cookies.set("dashboard_session", make_session(repo))
    c.headers["Origin"] = FRONTEND
    r = c.get(URL, params={"id": "1"})
    assert (r.status_code, r.json()["error"]) == (403, "not_bot_owner")


@pytest.mark.parametrize(
    "params", [{"id": ""}, {"id": "abc"}, {"id": "0"}, {"id": "-1"}, {"id": str(2**64)}, {"id": "1", "channel_id": "x"}]
)
def test_invalid_id(owner, params):
    r = owner.get(URL, params=params)
    assert (r.status_code, r.json()["error"]) == (400, "invalid_id")


def test_bot_not_ready(owner, world):
    world.ready = False
    r = owner.get(URL, params={"id": "1"})
    assert (r.status_code, r.json()["error"]) == (503, "bot_unavailable")


def test_nothing_found_returns_snowflake_time(owner):
    body = owner.get(URL, params={"id": "419131103836635136"}).json()
    assert body["matches"] == []
    assert body["created_at"] == discord.utils.snowflake_time(419131103836635136).isoformat()


def test_user_with_mutual_guilds(owner, world):
    role = fake_role(30)
    guild = fake_guild(10, members={5: fake_member(role)}, chunked=False)
    world.guilds.append(guild)
    world.users[5] = fake_user(5, [guild])
    body = owner.get(URL, params={"id": "5"}).json()
    assert body["member_cache_complete"] is False
    (user,) = body["matches"]
    assert {k: user[k] for k in ("kind", "name", "username", "bot", "system", "created_at")} == {
        "kind": "user",
        "name": "Alice",
        "username": "alice",
        "bot": False,
        "system": False,
        "created_at": AT.isoformat(),
    }
    assert user["guilds"] == [
        {
            "guild": {"id": "10", "name": "g10", "icon_url": None},
            "member": {
                "nick": "暱稱",
                "top_role": {"id": "30", "name": "role30"},
                "joined_at": AT.isoformat(),
                "timed_out": True,
                "status": "idle",
                "activity": "Minecraft",
            },
        }
    ]


def test_user_status_unknown_without_presence_intent(owner, world):
    world.intents.presences = False
    guild = fake_guild(10, members={5: fake_member(fake_role(30))})
    world.guilds.append(guild)
    world.users[5] = fake_user(5, [guild])
    member = owner.get(URL, params={"id": "5"}).json()["matches"][0]["guilds"][0]["member"]
    assert (member["status"], member["activity"]) == (None, None)


def test_user_fetched_when_not_cached(owner, world):
    world.fetched[6] = fake_user(6)
    assert kinds(owner.get(URL, params={"id": "6"}).json()) == ["user"]


@pytest.mark.parametrize(("status", "expected"), [(400, []), (429, [{"kind": "user", "error": "unavailable"}])])
def test_user_fetch_errors(owner, world, status, expected):
    world.fetch_error = http_error(discord.HTTPException, status)
    assert owner.get(URL, params={"id": "6"}).json()["matches"] == expected


def test_channel(owner, world):
    guild = fake_guild(10)
    world.channels[20] = fake_channel(20, guild=guild)
    (channel,) = owner.get(URL, params={"id": "20"}).json()["matches"]
    assert channel == {
        "kind": "channel",
        "id": "20",
        "name": "c20",
        "type": "text",
        "category": {"id": "50", "name": "類別"},
        "guild": {"id": "10", "name": "g10", "icon_url": None},
        "created_at": AT.isoformat(),
    }


def test_guild_without_everyone_role(owner, world):
    world.guilds.append(fake_guild(10))
    (guild,) = owner.get(URL, params={"id": "10"}).json()["matches"]
    assert guild == {
        "kind": "guild",
        "id": "10",
        "name": "g10",
        "icon_url": None,
        "owner": {"id": "7", "name": None, "avatar_url": None},
        "member_count": 12,
        "text_channels": 2,
        "voice_channels": 1,
        "verification_level": "medium",
        "created_at": AT.isoformat(),
    }


def test_role_without_guild_hint(owner, world):
    world.guilds.extend([fake_guild(10), fake_guild(11, roles=[fake_role(30)])])
    (role,) = owner.get(URL, params={"id": "30"}).json()["matches"]
    assert role == {
        "kind": "role",
        "id": "30",
        "name": "role30",
        "guild": {"id": "11", "name": "g11", "icon_url": None},
        "position": 3,
        "color": "#3498db",
        "permissions": str(2**40 + 8),
    }


def test_role_default_color_is_null(owner, world):
    world.guilds.append(fake_guild(11, roles=[fake_role(30, color=0)]))
    assert owner.get(URL, params={"id": "30"}).json()["matches"][0]["color"] is None


def test_same_id_matches_several_kinds(owner, world):
    guild = fake_guild(10)
    world.guilds.append(guild)
    world.channels[10] = fake_channel(10, guild=guild)
    assert kinds(owner.get(URL, params={"id": "10"}).json()) == ["channel", "guild"]


def test_message(owner, world):
    guild = fake_guild(10)
    world.channels[20] = fake_channel(20, guild=guild, messages={40: fake_message(40, content="哈囉", guild=guild)})
    body = owner.get(URL, params={"id": "40", "channel_id": "20"}).json()
    (message,) = body["matches"]
    assert message["author"] == {"id": "5", "name": "作者", "avatar_url": "https://cdn/b.png"}
    assert (message["content"], message["content_hidden"]) == ("哈囉", False)
    assert message["channel"] == {"id": "20", "name": "c20"}
    assert message["embeds"][0]["title"] == "標題"


@pytest.mark.parametrize(
    ("mentions", "author", "hidden"), [((), 5, True), ((SimpleNamespace(id=ME),), 5, False), ((), ME, False)]
)
def test_message_content_hidden_without_intent(owner, world, mentions, author, hidden):
    world.intents.message_content = False
    guild = fake_guild(10)
    msg = fake_message(40, content="", guild=guild, author_id=author, mentions=mentions)
    world.channels[20] = fake_channel(20, guild=guild, messages={40: msg})
    message = owner.get(URL, params={"id": "40", "channel_id": "20"}).json()["matches"][0]
    assert message["content_hidden"] is hidden


def test_message_empty_content_with_intent_is_not_hidden(owner, world):
    guild = fake_guild(10)
    world.channels[20] = fake_channel(20, guild=guild, messages={40: fake_message(40, content="", guild=guild)})
    assert owner.get(URL, params={"id": "40", "channel_id": "20"}).json()["matches"][0]["content_hidden"] is False


@pytest.mark.parametrize(
    ("channel", "expected"),
    [
        (None, [{"kind": "message", "error": "channel_not_found"}]),
        (fake_channel(20, messageable=False), [{"kind": "message", "error": "channel_not_found"}]),
        (fake_channel(20, fetch_error=http_error(discord.Forbidden, 403)), [{"kind": "message", "error": "forbidden"}]),
        (fake_channel(20, messages={}), []),
    ],
)
def test_message_errors(owner, world, channel, expected):
    if channel is not None:
        world.channels[20] = channel
    body = owner.get(URL, params={"id": "40", "channel_id": "20"}).json()
    assert [m for m in body["matches"] if m["kind"] == "message"] == expected
