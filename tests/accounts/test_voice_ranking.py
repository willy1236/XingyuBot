"""成員看的伺服器語音排行 /dashboard/personal/voice-ranking/{guild_id}（假 auth server、假 bot，真實 PostgreSQL）。"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from starDiscord.cmds import task as voice_task
from starlib import sclient
from starlib.database import VoiceTime
from starServer.dashboard import personal, voice_ranking
from tests.helpers.accounts import OTHER_ID, account
from tests.helpers.dashboard_auth import USER_ID, make_app, make_session

pytestmark = pytest.mark.usefixtures("dashboard_env")

OWN = int(USER_ID)
OTHER = int(OTHER_ID)
GUILD = 7001
ALICE, LEFT = 8001, 8003


class FakeGuild:
    id = GUILD
    name = "快樂營"

    def __init__(self, members: set[int]):
        self.members = members

    def get_member(self, uid: int):
        if uid not in self.members:
            return None
        return SimpleNamespace(display_name=f"m{uid}", display_avatar=SimpleNamespace(url=f"https://cdn/{uid}.png"))


class FakeBot:
    def __init__(self, guild: FakeGuild):
        self.guild = guild
        self._pool = ThreadPoolExecutor(max_workers=1)

    def is_ready(self):
        return True

    def get_guild(self, gid: int):
        return self.guild if gid == GUILD else None

    def submit(self, coro):
        return self._pool.submit(asyncio.run, coro)


@pytest.fixture
def guild(repo, dashboard_env, monkeypatch) -> FakeGuild:
    g = FakeGuild({OWN, ALICE})
    monkeypatch.setattr(voice_ranking, "sqldb", repo)
    monkeypatch.setattr(voice_task, "voice_times", {})
    monkeypatch.setattr(sclient, "bot", FakeBot(g))

    async def no_identity(discord_id, *, create=True):
        return None

    monkeypatch.setattr(personal, "resolve_identity", no_identity)
    return g


@pytest.fixture
def client(guild, repo) -> TestClient:
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
    make_session(repo)
    c.cookies.set("dashboard_session", "sid")
    return c


def seed(repo, minutes_by_uid: dict[int, int]):
    for uid, m in minutes_by_uid.items():
        repo.session.add(VoiceTime(discord_id=uid, guild_id=GUILD, total_minute=timedelta(minutes=m)))
    repo.session.commit()


def get(client, guild_id=GUILD, **params):
    return client.get(f"/dashboard/personal/voice-ranking/{guild_id}", params=params)


def test_full_ranking_with_mine(client, repo):
    seed(repo, {ALICE: 300, OWN: 60, LEFT: 90})
    body = get(client).json()
    assert body["guild_name"] == "快樂營" and body["total"] == 3
    assert [(i["rank"], i["member"]["id"], i["minutes"], i["mine"]) for i in body["items"]] == [
        (1, str(ALICE), 300, False),
        (2, str(LEFT), 90, False),
        (3, str(OWN), 60, True),
    ]
    assert body["items"][1]["member"] == {"id": str(LEFT), "name": None, "avatar_url": None, "left": True}
    assert body["mine"] == [{"rank": 3, "member": body["items"][2]["member"], "minutes": 60}]


def test_paging_keeps_rank_and_mine(client, repo):
    seed(repo, {**{9000 + i: 100 - i for i in range(5)}, OWN: 1})
    body = get(client, offset=2, limit=2).json()
    assert body["total"] == 6
    assert [i["rank"] for i in body["items"]] == [3, 4]
    assert [m["rank"] for m in body["mine"]] == [6]


def test_unsaved_minutes_counted(client, repo):
    seed(repo, {ALICE: 30})
    voice_task.voice_times[GUILD] = {OWN: timedelta(minutes=40)}
    assert [i["member"]["id"] for i in get(client).json()["items"]] == [str(OWN), str(ALICE)]


def test_linked_discord_membership_counts(client, guild, dashboard_env):
    guild.members = {OTHER}
    dashboard_env.directory.accounts[OWN] = account(uuid4(), (OWN, OTHER))
    assert get(client).status_code == 200


def test_not_member_forbidden(client, guild):
    guild.members = {ALICE}
    res = get(client)
    assert (res.status_code, res.json()) == (403, {"error": "not_member"})


def test_bot_not_in_guild(client):
    res = get(client, guild_id=1234)
    assert (res.status_code, res.json()) == (404, {"error": "bot_not_in_guild"})


def test_limit_capped(client):
    assert get(client, limit=voice_ranking.PAGE_SIZE + 1).status_code == 400


def test_requires_session(client):
    client.cookies.clear()
    assert get(client).status_code == 401
