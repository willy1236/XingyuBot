"""個人區紀錄 /dashboard/personal/records/*（假 auth server、假 bot，真實 PostgreSQL）。"""

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
from starServer.dashboard import personal, personal_records, voice_ranking
from tests.helpers.accounts import OTHER_ID, account
from tests.helpers.dashboard_auth import USER_ID, make_app, make_session

pytestmark = pytest.mark.usefixtures("dashboard_env")

OWN = int(USER_ID)
OTHER = int(OTHER_ID)
HERE, GONE = 7001, 7002
NOW = nowtz().replace(microsecond=0)


class FakeGuild:
    id = HERE
    name = "快樂營"
    #: 目前在伺服器裡的成員
    members: set[int] = {OWN}

    def get_member(self, uid: int):
        return SimpleNamespace() if uid in self.members else None


class FakeBot:
    def __init__(self, ready: bool = True):
        self.ready = ready
        self._pool = ThreadPoolExecutor(max_workers=1)

    def is_ready(self):
        return self.ready

    def get_guild(self, gid: int):
        return FakeGuild() if gid == HERE else None

    def submit(self, coro):
        return self._pool.submit(asyncio.run, coro)


@pytest.fixture
def client(repo, dashboard_env, monkeypatch) -> TestClient:
    monkeypatch.setattr(personal_records, "sqldb", repo)
    monkeypatch.setattr(voice_ranking, "sqldb", repo)
    monkeypatch.setattr(voice_task, "voice_times", {})
    monkeypatch.setattr(FakeGuild, "members", {OWN})
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
    def seed(self, repo):
        repo.session.add_all(
            [
                VoiceTime(discord_id=OWN, guild_id=GONE, total_minute=timedelta(minutes=5)),
                VoiceTime(discord_id=OWN, guild_id=HERE, total_minute=timedelta(hours=2, minutes=7, seconds=40)),
                VoiceTime(discord_id=OTHER, guild_id=HERE, total_minute=timedelta(hours=99)),
            ]
        )
        repo.session.commit()

    def test_sorted_desc_with_rank_and_unknown_guild(self, client, repo):
        self.seed(repo)
        assert get(client, "voice").json() == {
            "items": [
                {
                    "guild_id": str(HERE),
                    "guild_name": "快樂營",
                    "minutes": 127,
                    "rank": 2,
                    "ranked": 2,
                    "ranking_visible": True,
                },
                {
                    "guild_id": str(GONE),
                    "guild_name": None,
                    "minutes": 5,
                    "rank": None,
                    "ranked": None,
                    "ranking_visible": False,
                },
            ]
        }

    def test_unsaved_minutes_change_minutes_and_rank(self, client, repo):
        self.seed(repo)
        voice_task.voice_times[HERE] = {OWN: timedelta(hours=100)}
        item = get(client, "voice").json()["items"][0]
        assert (item["minutes"], item["rank"]) == (6127, 1)

    def test_unsaved_only_guild_listed(self, client):
        voice_task.voice_times[HERE] = {OWN: timedelta(minutes=3)}
        items = get(client, "voice").json()["items"]
        assert [(i["guild_id"], i["minutes"], i["rank"], i["ranked"]) for i in items] == [(str(HERE), 3, 1, 1)]

    def test_ranking_hidden_after_leaving_guild(self, client, repo, monkeypatch):
        self.seed(repo)
        monkeypatch.setattr(FakeGuild, "members", set())
        item = get(client, "voice").json()["items"][0]
        assert (item["rank"], item["ranking_visible"]) == (2, False)

    def test_unsaved_only_guild_skipped_after_bot_left(self, client):
        voice_task.voice_times[GONE] = {OWN: timedelta(minutes=3)}
        assert get(client, "voice").json() == {"items": []}

    def test_empty(self, client):
        assert get(client, "voice").json() == {"items": []}


class TestWarnings:
    def seed(self, repo, count=1):
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

    def test_fields_without_moderator(self, client, repo):
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

    def test_paging(self, client, repo):
        self.seed(repo, 25)
        first = get(client, "warnings").json()
        assert (len(first["items"]), first["total"]) == (20, 25)
        rest = get(client, "warnings", offset=20).json()
        assert [i["reason"] for i in rest["items"]] == ["r4", "r3", "r2", "r1", "r0"]

    def test_limit_capped(self, client):
        assert get(client, "warnings", limit=21).status_code == 400


class TestPolls:
    def test_multi_choice_merged_to_one(self, client, repo):
        poll = Poll(title="午餐", creator_id=1, created_at=NOW, guild_id=HERE)
        repo.session.add(poll)
        repo.session.commit()
        pid = poll.poll_id
        repo.session.add_all(
            [
                PollOption(poll_id=pid, option_id=1, option_name="麵"),
                PollOption(poll_id=pid, option_id=2, option_name="飯"),
            ]
        )
        for opt, mins in ((2, 1), (1, 3)):
            repo.session.add(
                UserPoll(poll_id=pid, discord_id=OWN, vote_option=opt, vote_at=NOW - timedelta(minutes=mins))
            )
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

    def test_paging_counts_polls_not_votes(self, client, repo):
        for i in range(3):
            poll = Poll(title=f"p{i}", creator_id=1, created_at=NOW, guild_id=HERE)
            repo.session.add(poll)
            repo.session.commit()
            for opt in (1, 2):
                repo.session.add(
                    UserPoll(
                        poll_id=poll.poll_id, discord_id=OWN, vote_option=opt, vote_at=NOW - timedelta(minutes=10 - i)
                    )
                )
        repo.session.commit()
        body = get(client, "polls", offset=1, limit=1).json()
        assert body["total"] == 3 and [i["title"] for i in body["items"]] == ["p1"]


class TestBets:
    def test_fields_via_place_bet(self, client, repo):
        repo.session.add(
            Bet(bet_id=50, title="誰會贏", blue_title="藍隊", pink_title="粉隊", is_on=True, created_at=NOW)
        )
        repo.session.commit()
        repo.place_bet(50, OWN, 2, 30)
        repo.place_bet(50, OTHER, 1, 5)
        item = get(client, "bets").json()["items"][0]
        assert get(client, "bets").json()["total"] == 1
        assert {k: item[k] for k in ("id", "title", "option", "amount")} == {
            "id": 50,
            "title": "誰會贏",
            "option": "粉隊",
            "amount": 30,
        }
        assert item["at"] is not None

    def test_null_time_sorted_last(self, client, repo):
        repo.session.add_all(
            [
                Bet(bet_id=50, title="舊", blue_title="藍", pink_title="粉", is_on=False, created_at=NOW),
                Bet(bet_id=51, title="新", blue_title="藍", pink_title="粉", is_on=False, created_at=NOW),
                UserBet(bet_id=50, discord_id=OWN, bet_option=1, bet_amount=1, bet_at=None),
                UserBet(bet_id=51, discord_id=OWN, bet_option=1, bet_amount=1, bet_at=NOW),
            ]
        )
        repo.session.commit()
        items = get(client, "bets").json()["items"]
        assert [(i["title"], i["at"]) for i in items] == [("新", NOW.isoformat()), ("舊", None)]


class TestGiveaways:
    def test_results(self, client, repo):
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
                    giveaway_id=gid,
                    user_id=OWN,
                    user_weight=1,
                    join_at=NOW - timedelta(minutes=3 - n),
                    is_winner=winner,
                )
            )
        repo.session.commit()
        items = get(client, "giveaways").json()["items"]
        assert [(i["prize"], i["result"], i["guild_name"]) for i in items] == [
            ("獎C", "pending", "快樂營"),
            ("獎B", "lost", "快樂營"),
            ("獎A", "won", "快樂營"),
        ]

    def test_deleted_giveaway(self, client, repo):
        repo.session.add(GiveawayUser(giveaway_id=9999, user_id=OWN, user_weight=1, join_at=NOW, is_winner=False))
        repo.session.commit()
        item = get(client, "giveaways").json()["items"][0]
        assert (item["result"], item["prize"], item["guild_name"]) == ("deleted", None, None)


class TestBotNotReady:
    def test_no_records_needs_no_names(self, client, monkeypatch):
        monkeypatch.setattr(sclient, "bot", FakeBot(ready=False))
        res = get(client, "voice")
        assert res.status_code == 200  # 沒有任何紀錄時不需要伺服器名稱
        res = get(client, "warnings")
        assert res.status_code == 200

    def test_with_records_503(self, client, repo, monkeypatch):
        repo.session.add(VoiceTime(discord_id=OWN, guild_id=HERE, total_minute=timedelta(minutes=1)))
        repo.session.commit()
        monkeypatch.setattr(sclient, "bot", FakeBot(ready=False))
        res = get(client, "voice")
        assert (res.status_code, res.json()) == (503, {"error": "bot_unavailable"})
