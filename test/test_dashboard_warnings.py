"""伺服器管理後台 W-01：警告紀錄清單、篩選、警告單、成員跨群紀錄與成員搜尋（假 Discord，真實 PostgreSQL）。"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from test_dashboard_auth import dashboard_env, make_app, make_session  # noqa: F401  (fixture 與 helper)
from test_dashboard_guilds import MANAGE_CHANNELS, g, seed_token
from test_dashboard_guilds import discord as discord_env  # noqa: F401  (fixture)
from test_dashboard_notifies import GUILD_ID, fake_bot
from test_identity import repo  # noqa: F401

from starlib import sclient
from starlib.database import UserModerate, WarningType
from starlib.utils import nowtz
from starServer.dashboard import warnings

BAN_MEMBERS = 0x4
URL = f"/dashboard/guilds/{GUILD_ID}/warnings"
OTHER_GUILD = GUILD_ID + 1
MOD = 8001
ALICE = 8002
BOB = 8003
LEFT = 8004


def _member(uid: int, name: str, username: str):
    return SimpleNamespace(
        id=uid,
        display_name=name,
        name=username,
        global_name=None,
        display_avatar=SimpleNamespace(url=f"https://cdn/{uid}.png"),
    )


class FakeGuild:
    def __init__(self):
        self.id = GUILD_ID
        self.name = "測試伺服器"
        self.members = [_member(MOD, "管理員", "mod"), _member(ALICE, "愛麗絲", "alice"), _member(BOB, "鮑伯", "bob")]

    def get_member(self, uid: int):
        return next((m for m in self.members if m.id == uid), None)


def _bot(guild):
    bot = fake_bot(guild)
    bot.get_user = lambda uid: None
    bot.get_guild = lambda gid: guild if gid == GUILD_ID else None
    return bot


@pytest.fixture
def client(discord_env, repo, dashboard_env, monkeypatch) -> TestClient:  # noqa: F811
    seed_token(repo, dashboard_env.credential_id)
    make_session(repo)
    discord_env.guilds = [g(str(GUILD_ID), "guild", BAN_MEMBERS)]
    monkeypatch.setattr(warnings, "sqldb", repo)
    monkeypatch.setattr(sclient, "bot", _bot(FakeGuild()))
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
    c.cookies.set("dashboard_session", "sid")
    c.repo = repo  # pyright: ignore[reportAttributeAccessIssue]
    c.discord_env = discord_env  # pyright: ignore[reportAttributeAccessIssue]
    c.monkeypatch = monkeypatch  # pyright: ignore[reportAttributeAccessIssue]
    return c


def add_record(
    client,
    *,
    target=ALICE,
    kind=WarningType.Warning,
    guild=GUILD_ID,
    guild_only=True,
    reason="原因",
    minutes_ago=0,
    last_time=None,
) -> UserModerate:
    row = UserModerate(
        discord_id=target,
        moderate_type=kind,
        moderate_user=MOD,
        create_guild=guild,
        create_time=nowtz().replace(microsecond=0) - timedelta(minutes=minutes_ago),
        reason=reason,
        last_time=last_time,
        guild_only=guild_only,
        officially_given=False,
    )
    client.repo.add(row)
    return row


class TestPermission:
    def test_ban_only_user_can_view(self, client):
        assert client.get(URL).status_code == 200

    def test_no_entry_permission_is_403(self, client):
        client.discord_env.guilds = [g(str(GUILD_ID), "guild", 0)]
        assert client.get(URL).status_code == 403
        assert client.get(f"{URL}/member-search", params={"q": "a"}).status_code == 403
        assert client.get(f"{URL}/members/{ALICE}").status_code == 403

    def test_manage_channels_user_can_view(self, client):
        client.discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_CHANNELS)]
        assert client.get(URL).status_code == 200


class TestList:
    def test_empty(self, client):
        body = client.get(URL).json()
        assert body["warnings"] == []
        assert body["total"] == 0
        assert body["has_next"] is False

    def test_newest_first_with_fields(self, client):
        old = add_record(client, reason="舊", minutes_ago=30)
        new = add_record(
            client, kind=WarningType.Timeout, target=BOB, reason="新", last_time=timedelta(minutes=10), guild_only=False
        )
        rows = client.get(URL).json()["warnings"]
        assert [r["id"] for r in rows] == [new.warning_id, old.warning_id]
        first = rows[0]
        assert first["kind"] == "timeout"
        assert first["target"] == {
            "id": str(BOB),
            "name": "鮑伯",
            "avatar_url": f"https://cdn/{BOB}.png",
            "left": False,
        }
        assert first["moderator"]["name"] == "管理員"
        assert first["reason"] == "新"
        assert first["duration_seconds"] == 600
        assert first["cross_guild"] is True
        assert rows[1]["cross_guild"] is False
        assert rows[1]["duration_seconds"] is None

    def test_only_this_guild_records(self, client):
        add_record(client, reason="別處", guild=OTHER_GUILD, guild_only=False)
        add_record(client, reason="這裡")
        assert [r["reason"] for r in client.get(URL).json()["warnings"]] == ["這裡"]

    def test_left_member_flagged(self, client):
        add_record(client, target=LEFT)
        target = client.get(URL).json()["warnings"][0]["target"]
        assert target["left"] is True
        assert target["name"] is None
        assert target["id"] == str(LEFT)

    def test_filter_by_member_and_kind(self, client):
        add_record(client, target=ALICE, kind=WarningType.Warning)
        add_record(client, target=ALICE, kind=WarningType.Ban)
        add_record(client, target=BOB, kind=WarningType.Warning)
        by_member = client.get(URL, params={"member": str(ALICE)}).json()["warnings"]
        assert {r["target"]["id"] for r in by_member} == {str(ALICE)}
        assert len(by_member) == 2
        by_kind = client.get(URL, params={"kind": "warning"}).json()["warnings"]
        assert {r["kind"] for r in by_kind} == {"warning"}
        assert len(by_kind) == 2
        both = client.get(URL, params={"member": str(ALICE), "kind": "ban"}).json()
        assert [r["kind"] for r in both["warnings"]] == ["ban"]
        assert both["total"] == 1

    def test_invalid_filters_are_400(self, client):
        assert client.get(URL, params={"kind": "nope"}).status_code == 400
        assert client.get(URL, params={"member": "abc"}).status_code == 400
        assert client.get(URL, params={"page": 0}).status_code == 400

    def test_paging_50_per_page(self, client):
        for i in range(55):
            add_record(client, reason=f"r{i}", minutes_ago=i)
        first = client.get(URL).json()
        assert len(first["warnings"]) == 50
        assert first["total"] == 55
        assert first["has_next"] is True
        second = client.get(URL, params={"page": 2}).json()
        assert len(second["warnings"]) == 5
        assert second["has_next"] is False
        assert second["warnings"][0]["reason"] == "r50"

    def test_sheet_matches_embed(self, client):
        row = add_record(client, reason="測試原因", guild_only=True)
        item = client.get(URL).json()["warnings"][0]
        expected = row.embed(sclient.bot)
        assert item["sheet"] == {"title": expected.author.name, "description": expected.description}
        assert f"編號：{row.warning_id}" in item["sheet"]["description"]
        assert "測試原因" in item["sheet"]["description"]


class TestMemberRecords:
    def test_cross_guild_plus_this_guild_only(self, client):
        add_record(client, target=ALICE, guild=OTHER_GUILD, guild_only=False, reason="別處跨群")
        add_record(client, target=ALICE, guild=OTHER_GUILD, guild_only=True, reason="別處僅限該處")
        add_record(client, target=ALICE, guild=GUILD_ID, guild_only=True, reason="本處僅限本處")
        add_record(client, target=BOB, guild=GUILD_ID, reason="別人")
        body = client.get(f"{URL}/members/{ALICE}").json()
        assert body["member"]["name"] == "愛麗絲"
        assert {r["reason"] for r in body["warnings"]} == {"別處跨群", "本處僅限本處"}
        by_reason = {r["reason"]: r for r in body["warnings"]}
        assert by_reason["別處跨群"]["this_guild"] is False
        assert by_reason["別處跨群"]["cross_guild"] is True

    def test_not_member_is_400(self, client):
        response = client.get(f"{URL}/members/{LEFT}")
        assert response.status_code == 400
        assert response.json()["error"] == "not_member"

    def test_no_records(self, client):
        assert client.get(f"{URL}/members/{ALICE}").json()["warnings"] == []


class TestMemberSearch:
    def search(self, client, q):
        return client.get(f"{URL}/member-search", params={"q": q}).json()["members"]

    def test_by_name_username_and_id(self, client):
        assert [m["id"] for m in self.search(client, "愛")] == [str(ALICE)]
        assert [m["id"] for m in self.search(client, "BOB")] == [str(BOB)]
        assert [m["id"] for m in self.search(client, str(MOD))] == [str(MOD)]

    def test_empty_query_returns_nothing(self, client):
        assert self.search(client, "  ") == []

    def test_limit_25(self, client):
        guild = FakeGuild()
        guild.members = [_member(1000 + i, f"user{i:02d}", f"u{i}") for i in range(40)]
        client.monkeypatch.setattr(sclient, "bot", _bot(guild))
        assert len(self.search(client, "user")) == 25
