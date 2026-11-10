"""伺服器管理後台 G-01、G-02：抽獎清單、詳情、參加者與中獎者、提前結束與重抽（假 Discord，真實 PostgreSQL）。"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from test_dashboard_auth import dashboard_env, make_app, make_session  # noqa: F401  (fixture 與 helper)
from test_dashboard_guilds import MANAGE_CHANNELS, MANAGE_MESSAGES, g, seed_token
from test_dashboard_guilds import discord as discord_env  # noqa: F401  (fixture)
from test_dashboard_notifies import GUILD_ID, fake_bot
from test_identity import repo  # noqa: F401

from starlib import sclient
from starlib.database import Giveaway, GiveawayUser
from starlib.utils import nowtz
from starServer.dashboard import giveaways

URL = f"/dashboard/guilds/{GUILD_ID}/giveaways"
CREATOR = 7001
MEMBER = 7002
LEFT = 7003


class FakeGuild:
    def __init__(self):
        self.id = GUILD_ID
        self.members = {
            CREATOR: SimpleNamespace(display_name="發起人", display_avatar=SimpleNamespace(url="https://cdn/c.png")),
            MEMBER: SimpleNamespace(display_name="成員", display_avatar=SimpleNamespace(url="https://cdn/m.png")),
        }
        self.channels = {500: SimpleNamespace(name="抽獎頻道")}

    def get_member(self, uid: int):
        return self.members.get(uid)

    def get_channel(self, cid: int):
        return self.channels.get(cid)


@pytest.fixture
def client(discord_env, repo, dashboard_env, monkeypatch) -> TestClient:  # noqa: F811
    seed_token(repo, dashboard_env.credential_id)
    make_session(repo)
    discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_MESSAGES)]
    monkeypatch.setattr(giveaways, "sqldb", repo)
    bot = fake_bot(FakeGuild())
    bot.get_user = lambda uid: None
    monkeypatch.setattr(sclient, "bot", bot)
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
    c.cookies.set("dashboard_session", "sid")
    c.repo = repo  # pyright: ignore[reportAttributeAccessIssue]
    c.discord_env = discord_env  # pyright: ignore[reportAttributeAccessIssue]
    c.monkeypatch = monkeypatch  # pyright: ignore[reportAttributeAccessIssue]
    return c


def add_giveaway(client, *, prize="獎品", guild_id=GUILD_ID, is_on=False, created_days_ago=1, ended_days_ago=0) -> Giveaway:
    now = nowtz().replace(microsecond=0)
    row = Giveaway(
        guild_id=guild_id,
        channel_id=500,
        message_id=900,
        creator_id=CREATOR,
        prize_name=prize,
        winner_count=1,
        created_at=now - timedelta(days=created_days_ago),
        end_at=(now + timedelta(hours=2)) if is_on else (now - timedelta(days=ended_days_ago)),
        is_on=is_on,
        description=None,
        redraw_count=0,
    )
    client.repo.add(row)
    return row


def join(client, giveaway_id: int, user_id: int, winner: bool = False, minutes: int = 0):
    join_at = nowtz().replace(microsecond=0) + timedelta(minutes=minutes)
    client.repo.add(GiveawayUser(giveaway_id=giveaway_id, user_id=user_id, user_weight=1, join_at=join_at, is_winner=winner))


class TestList:
    def test_empty(self, client):
        body = client.get(URL).json()
        assert body["giveaways"] == []
        assert body["has_next"] is False

    def test_active_first_then_ended_newest_first(self, client):
        add_giveaway(client, prize="舊結束", ended_days_ago=5)
        add_giveaway(client, prize="新結束", ended_days_ago=1)
        add_giveaway(client, prize="進行中", is_on=True)
        rows = client.get(URL).json()["giveaways"]
        assert [r["prize_name"] for r in rows] == ["進行中", "新結束", "舊結束"]
        assert [r["status"] for r in rows] == ["active", "ended", "ended"]

    def test_summary_fields(self, client):
        gw = add_giveaway(client, is_on=True)
        join(client, gw.id, MEMBER)
        row = client.get(URL).json()["giveaways"][0]
        assert row["id"] == gw.id
        assert row["participant_count"] == 1
        assert row["creator_id"] == str(CREATOR)
        assert row["creator_name"] == "發起人"
        assert row["channel_name"] == "抽獎頻道"
        assert row["message_url"] == f"https://discord.com/channels/{GUILD_ID}/500/900"
        # 進行中顯示預計開獎時間（deadline）
        assert row["ends_at"] == gw.deadline.isoformat()

    def test_missing_channel_name_is_null(self, client):
        gw = add_giveaway(client, is_on=True)
        gw.channel_id = 999
        client.repo.merge(gw)
        row = client.get(URL).json()["giveaways"][0]
        assert row["channel_id"] == "999"
        assert row["channel_name"] is None

    def test_default_hides_older_than_90_days_but_all_shows_them(self, client):
        add_giveaway(client, prize="很久以前", created_days_ago=100, ended_days_ago=99)
        add_giveaway(client, prize="最近", created_days_ago=3, ended_days_ago=2)
        assert [r["prize_name"] for r in client.get(URL).json()["giveaways"]] == ["最近"]
        assert [r["prize_name"] for r in client.get(URL, params={"all": "true"}).json()["giveaways"]] == ["最近", "很久以前"]

    def test_active_is_not_limited_by_90_days(self, client):
        add_giveaway(client, prize="久遠進行中", is_on=True, created_days_ago=100)
        assert [r["prize_name"] for r in client.get(URL).json()["giveaways"]] == ["久遠進行中"]

    def test_only_this_guild(self, client):
        add_giveaway(client, prize="別的伺服器", guild_id=GUILD_ID + 1)
        add_giveaway(client, prize="這裡")
        assert [r["prize_name"] for r in client.get(URL).json()["giveaways"]] == ["這裡"]

    def test_paging_active_only_on_first_page(self, client):
        add_giveaway(client, prize="進行中", is_on=True)
        for i in range(25):
            add_giveaway(client, prize=f"結束{i:02d}", created_days_ago=2, ended_days_ago=1)
        first = client.get(URL).json()
        # 進行中不算在 20 筆內
        assert len(first["giveaways"]) == 21
        assert first["giveaways"][0]["prize_name"] == "進行中"
        assert first["has_next"] is True
        second = client.get(URL, params={"page": 2}).json()
        assert len(second["giveaways"]) == 5
        assert all(r["status"] == "ended" for r in second["giveaways"])
        assert second["has_next"] is False
        ids = {r["id"] for r in first["giveaways"]} | {r["id"] for r in second["giveaways"]}
        assert len(ids) == 26

    def test_page_must_be_positive(self, client):
        assert client.get(URL, params={"page": 0}).status_code == 400

    def test_requires_manage_messages(self, client):
        client.discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_CHANNELS)]
        r = client.get(URL)
        assert r.status_code == 403
        assert r.json()["error"] == "no_permission"


class TestDetail:
    def test_participants_and_winners(self, client):
        gw = add_giveaway(client, prize="大獎")
        join(client, gw.id, MEMBER, winner=True, minutes=1)
        join(client, gw.id, LEFT, winner=True, minutes=2)
        join(client, gw.id, CREATOR, minutes=0)
        body = client.get(f"{URL}/{gw.id}").json()
        assert body["prize_name"] == "大獎"
        assert body["channel_name"] == "抽獎頻道"
        assert body["creator_name"] == "發起人"
        assert body["redraw_count"] == 0
        # 依加入時間排序
        assert [p["id"] for p in body["participants"]] == [str(CREATOR), str(MEMBER), str(LEFT)]
        assert [w["id"] for w in body["winners"]] == [str(MEMBER), str(LEFT)]
        member = body["participants"][1]
        assert member["name"] == "成員"
        assert member["avatar_url"] == "https://cdn/m.png"
        assert member["left"] is False
        # 已離開的成員仍列出，只有 ID
        left = body["participants"][2]
        assert left["left"] is True
        assert left["name"] is None

    def test_left_member_name_ignored_even_if_bot_knows_user(self, client):
        # 成員已離開本服，但 bot 在其他伺服器仍看得到使用者時，也不回名稱
        gw = add_giveaway(client)
        join(client, gw.id, LEFT)
        sclient.bot.get_user = lambda uid: SimpleNamespace(name="跨服名稱") if uid == LEFT else None
        left = client.get(f"{URL}/{gw.id}").json()["participants"][0]
        assert left["left"] is True
        assert left["name"] is None

    def test_redraw_count_reflects_db(self, client):
        gw = add_giveaway(client)
        gw.redraw_count = 3
        client.repo.merge(gw)
        assert client.get(f"{URL}/{gw.id}").json()["redraw_count"] == 3

    def test_other_guild_is_404(self, client):
        gw = add_giveaway(client, guild_id=GUILD_ID + 1)
        r = client.get(f"{URL}/{gw.id}")
        assert r.status_code == 404
        assert r.json()["error"] == "giveaway_not_found"

    def test_unknown_id_is_404(self, client):
        assert client.get(f"{URL}/999999").status_code == 404

    def test_requires_manage_messages(self, client):
        gw = add_giveaway(client)
        client.discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_CHANNELS)]
        assert client.get(f"{URL}/{gw.id}").status_code == 403
