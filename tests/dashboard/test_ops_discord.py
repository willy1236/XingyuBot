"""營運入口的 Discord 部分：目前所在的伺服器、每日人數、加入離開紀錄（真實 PostgreSQL，測完 rollback）。"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from starlib import sclient
from starlib.database import GuildMembershipEvent, UsersCountRecord
from starlib.utils import nowtz
from starServer.dashboard import ops_discord
from tests.helpers.dashboard_auth import FRONTEND, USER_ID, make_app, make_session

pytestmark = pytest.mark.usefixtures("dashboard_env")

BASE = "/dashboard/ops/discord"
NOW = nowtz().replace(microsecond=0)


def client_for(session_id: str) -> TestClient:
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
    c.cookies.set("dashboard_session", session_id)
    c.headers["Origin"] = FRONTEND
    return c


def fake_guild(guild_id: int, joined_days_ago: int | None):
    joined_at = None if joined_days_ago is None else NOW - timedelta(days=joined_days_ago)
    return SimpleNamespace(
        id=guild_id,
        name=f"g{guild_id}",
        icon=None,
        member_count=7,
        me=SimpleNamespace(joined_at=joined_at),
        owner_id=500 + guild_id,
        owner=None,
    )


@pytest.fixture
def bot(monkeypatch, repo):
    monkeypatch.setattr(ops_discord, "sqldb", repo)
    state = SimpleNamespace(owners={int(USER_ID)}, ready=True, guilds=[], users=[1, 2, 3])

    async def is_owner(user):
        return user.id in state.owners

    fake = SimpleNamespace(is_owner=is_owner, is_ready=lambda: state.ready, guilds=state.guilds, users=state.users)
    monkeypatch.setattr(sclient, "bot", fake)
    repo.session.query(GuildMembershipEvent).delete()
    repo.session.query(UsersCountRecord).delete()
    repo.session.flush()
    return state


@pytest.fixture
def owner(repo, bot) -> TestClient:
    return client_for(make_session(repo))


@pytest.mark.parametrize("path", [BASE, f"{BASE}/events"])
def test_non_owner_is_forbidden(repo, bot, path):
    bot.owners.clear()
    r = client_for(make_session(repo)).get(path)
    assert (r.status_code, r.json()["error"]) == (403, "not_bot_owner")


def test_overview_lists_live_guilds_newest_join_first(owner, bot):
    bot.guilds.extend([fake_guild(1, 30), fake_guild(2, 1), fake_guild(3, None)])
    live = owner.get(BASE).json()["live"]
    assert (live["guild_count"], live["user_count"]) == (3, 3)
    assert [g["id"] for g in live["guilds"]] == ["3", "2", "1"]
    assert live["guilds"][1]["joined_at"] == (NOW - timedelta(days=1)).isoformat()


def test_owner_with_and_without_member_cache(owner, bot):
    cached = fake_guild(1, 1)
    cached.owner = SimpleNamespace(display_name="群主", display_avatar=SimpleNamespace(url="https://cdn/a.png"))
    bot.guilds.extend([cached, fake_guild(2, 2)])
    owners = [g["owner"] for g in owner.get(BASE).json()["live"]["guilds"]]
    assert owners == [
        {"id": "501", "name": "群主", "avatar_url": "https://cdn/a.png"},
        {"id": "502", "name": None, "avatar_url": None},
    ]


def test_overview_live_is_null_when_bot_not_ready(owner, bot):
    bot.ready = False
    assert owner.get(BASE).json()["live"] is None


def test_overview_daily_within_days_oldest_first(owner, repo):
    today = NOW.date()
    for back in (0, 5, 40):
        repo.add(UsersCountRecord(record_date=today - timedelta(days=back), users_count=100 - back, servers_count=10))
    daily = owner.get(BASE, params={"days": 30}).json()["daily"]
    assert daily == [
        {"date": (today - timedelta(days=5)).isoformat(), "users": 95, "servers": 10},
        {"date": today.isoformat(), "users": 100, "servers": 10},
    ]


def test_events_newest_first_with_paging(owner, repo, monkeypatch):
    monkeypatch.setattr(ops_discord, "PAGE_SIZE", 2)
    for i, event in enumerate(["join", "leave", "join"]):
        repo.add(
            GuildMembershipEvent(
                guild_id=10**18 + i, guild_name=f"g{i}", event=event, at=NOW - timedelta(days=3 - i), source="gateway"
            )
        )
    first = owner.get(f"{BASE}/events").json()
    assert [e["guild_id"] for e in first["events"]] == [str(10**18 + 2), str(10**18 + 1)]
    assert first["has_next"] is True
    second = owner.get(f"{BASE}/events", params={"page": 2}).json()
    assert [e["event"] for e in second["events"]] == ["join"]
    assert second["has_next"] is False
