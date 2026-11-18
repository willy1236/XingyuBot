"""個人區紀錄 /dashboard/personal/records/*（假 auth server、假 bot，真實 PostgreSQL）。"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_dashboard_auth import (  # noqa: F401  (fixture 與 helper)
    USER_ID,
    dashboard_env,
    make_app,
    make_session,
)
from test_dashboard_domalyze_login import OTHER_ID, account
from test_identity import repo  # noqa: F401

from starlib import sclient
from starlib.database import (
    Bet,
    Giveaway,
    GiveawayUser,
    Poll,
    PollOption,
    UserBet,
    UserModerate,
    UserPoll,
    VoiceTime,
    WarningType,
)
from starlib.utils import nowtz
from starServer.dashboard import personal, personal_records

OWN = int(USER_ID)
OTHER = int(OTHER_ID)
HERE, GONE = 7001, 7002
NOW = nowtz().replace(microsecond=0)


class FakeBot:
    def __init__(self):
        self._pool = ThreadPoolExecutor(max_workers=1)

    def get_guild(self, gid: int):
        return SimpleNamespace(name="快樂營") if gid == HERE else None

    def submit(self, coro):
        return self._pool.submit(asyncio.run, coro)


@pytest.fixture
def client(repo, dashboard_env, monkeypatch) -> TestClient:  # noqa: F811
    monkeypatch.setattr(personal_records, "sqldb", repo)
    monkeypatch.setattr(sclient, "bot", FakeBot())

    async def no_identity(discord_id, *, create=True):
        return None

    monkeypatch.setattr(personal, "resolve_identity", no_identity)
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
    make_session(repo)
    c.cookies.set("dashboard_session", "sid")
    return c


def get(client, kind, discord_id=OWN, **params):
    return client.get(f"/dashboard/personal/records/{kind}", params={"discord_id": discord_id, **params})


class TestScope:
    @pytest.mark.parametrize("kind", ["voice", "warnings", "polls", "bets", "giveaways"])
    def test_other_discord_forbidden(self, client, kind):
        res = get(client, kind, OTHER)
        assert (res.status_code, res.json()) == (403, {"error": "no_permission"})

    def test_linked_discord_allowed(self, client, dashboard_env):
        dashboard_env.directory.accounts[OWN] = account(uuid4(), (OWN, OTHER))
        assert get(client, "warnings", OTHER).json() == {"items": [], "total": 0}

    def test_requires_session(self, client):
        client.cookies.clear()
        assert get(client, "voice").status_code == 401

    def test_unknown_kind(self, client):
        assert get(client, "nope").status_code == 400


class TestVoice:
    def test_sorted_desc_with_unknown_guild(self, client, repo):  # noqa: F811
        repo.session.add_all(
            [
                VoiceTime(discord_id=OWN, guild_id=GONE, total_minute=timedelta(minutes=5)),
                VoiceTime(discord_id=OWN, guild_id=HERE, total_minute=timedelta(hours=2, minutes=7, seconds=40)),
                VoiceTime(discord_id=OTHER, guild_id=HERE, total_minute=timedelta(hours=99)),
            ]
        )
        repo.session.commit()
        assert get(client, "voice").json() == {
            "items": [{"guild_name": "快樂營", "minutes": 127}, {"guild_name": None, "minutes": 5}]
        }

    def test_empty(self, client):
        assert get(client, "voice").json() == {"items": []}


class TestWarnings:
    def seed(self, repo, count=1):  # noqa: F811
        for i in range(count):
            repo.session.add(
                UserModerate(
                    discord_id=OWN,
                    moderate_type=WarningType.Timeout if i == 0 else WarningType.Warning,
                    moderate_user=999,
                    create_guild=HERE if i % 2 == 0 else GONE,
                    create_time=NOW - timedelta(minutes=count - i),
                    reason=f"r{i}",
                    last_time=timedelta(hours=1) if i == 0 else None,
                    guild_only=True,
                )
            )
        repo.session.commit()

    def test_fields_without_moderator(self, client, repo):  # noqa: F811
        self.seed(repo, 2)
        body = get(client, "warnings").json()
        assert body["total"] == 2
        assert body["items"][0] == {
            "id": body["items"][0]["id"],
            "guild_name": None,
            "type": "warning",
            "at": (NOW - timedelta(minutes=1)).isoformat(),
            "reason": "r1",
            "duration_seconds": None,
        }
        assert body["items"][1]["type"] == "timeout" and body["items"][1]["duration_seconds"] == 3600
        assert body["items"][1]["guild_name"] == "快樂營"

    def test_paging(self, client, repo):  # noqa: F811
        self.seed(repo, 25)
        first = get(client, "warnings").json()
        assert (len(first["items"]), first["total"]) == (20, 25)
        rest = get(client, "warnings", offset=20).json()
        assert [i["reason"] for i in rest["items"]] == ["r4", "r3", "r2", "r1", "r0"]

    def test_limit_capped(self, client):
        assert get(client, "warnings", limit=21).status_code == 400


class TestPolls:
    def test_multi_choice_merged_to_one(self, client, repo):  # noqa: F811
        poll = Poll(title="午餐", creator_id=1, created_at=NOW, guild_id=HERE)
        repo.session.add(poll)
        repo.session.commit()
        pid = poll.poll_id
        repo.session.add_all(
            [PollOption(poll_id=pid, option_id=1, option_name="麵"), PollOption(poll_id=pid, option_id=2, option_name="飯")]
        )
        for opt, mins in ((2, 1), (1, 3)):
            repo.session.add(UserPoll(poll_id=pid, discord_id=OWN, vote_option=opt, vote_at=NOW - timedelta(minutes=mins)))
        repo.session.add(UserPoll(poll_id=pid, discord_id=OTHER, vote_option=1, vote_at=NOW))
        repo.session.commit()
        assert get(client, "polls").json() == {
            "items": [
                {
                    "id": pid,
                    "guild_name": "快樂營",
                    "title": "午餐",
                    "options": ["麵", "飯"],
                    "at": (NOW - timedelta(minutes=3)).isoformat(),
                }
            ],
            "total": 1,
        }

    def test_paging_counts_polls_not_votes(self, client, repo):  # noqa: F811
        for i in range(3):
            poll = Poll(title=f"p{i}", creator_id=1, created_at=NOW, guild_id=HERE)
            repo.session.add(poll)
            repo.session.commit()
            for opt in (1, 2):
                repo.session.add(
                    UserPoll(poll_id=poll.poll_id, discord_id=OWN, vote_option=opt, vote_at=NOW - timedelta(minutes=10 - i))
                )
        repo.session.commit()
        body = get(client, "polls", offset=1, limit=1).json()
        assert body["total"] == 3 and [i["title"] for i in body["items"]] == ["p1"]


class TestBets:
    def test_fields(self, client, repo):  # noqa: F811
        repo.session.add(Bet(bet_id=50, title="誰會贏", blue_title="藍隊", pink_title="粉隊", is_on=False, created_at=NOW))
        repo.session.add(UserBet(bet_id=50, discord_id=OWN, bet_option=2, bet_amount=30, bet_at=NOW))
        repo.session.add(UserBet(bet_id=50, discord_id=OTHER, bet_option=1, bet_amount=5, bet_at=NOW))
        repo.session.commit()
        assert get(client, "bets").json() == {
            "items": [{"id": 50, "title": "誰會贏", "option": "粉隊", "amount": 30, "at": NOW.isoformat()}],
            "total": 1,
        }


class TestGiveaways:
    def test_results(self, client, repo):  # noqa: F811
        def giveaway(prize, is_on):
            g = Giveaway(
                guild_id=HERE, channel_id=1, creator_id=1, prize_name=prize, winner_count=1, created_at=NOW, is_on=is_on
            )
            repo.session.add(g)
            repo.session.commit()
            return g.id

        won, lost, pending = giveaway("獎A", False), giveaway("獎B", False), giveaway("獎C", True)
        for n, (gid, winner) in enumerate(((won, True), (lost, False), (pending, False))):
            repo.session.add(
                GiveawayUser(
                    giveaway_id=gid, user_id=OWN, user_weight=1, join_at=NOW - timedelta(minutes=3 - n), is_winner=winner
                )
            )
        repo.session.commit()
        items = get(client, "giveaways").json()["items"]
        assert [(i["prize"], i["result"], i["guild_name"]) for i in items] == [
            ("獎C", "pending", "快樂營"),
            ("獎B", "lost", "快樂營"),
            ("獎A", "won", "快樂營"),
        ]
