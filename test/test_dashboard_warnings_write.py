"""伺服器管理後台 W-02：後台警告、禁言、踢出、停權（假 Discord，真實 PostgreSQL，走真的 punish）。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from fastapi.testclient import TestClient
from test_dashboard_auth import FRONTEND, USER_ID, dashboard_env, make_app, make_session  # noqa: F401  (fixture 與 helper)
from test_dashboard_guilds import discord as discord_env  # noqa: F401  (fixture)
from test_dashboard_guilds import g, seed_token
from test_dashboard_notifies import GUILD_ID, fake_bot
from test_identity import repo  # noqa: F401

from starlib import moderation, sclient
from starlib.database import UserModerate, WarningType
from starServer.dashboard import guilds, warnings

KICK = 0x2
BAN = 0x4
MANAGE_MESSAGES = 0x2000
MODERATE = 0x10000000000
ALL = KICK | BAN | MANAGE_MESSAGES | MODERATE
URL = f"/dashboard/guilds/{GUILD_ID}/warnings"
ME = int(USER_ID)
ALICE = 8002
STRANGER = 9001
BOT_USER = 8100
CHANNEL = 700


def http_error(cls=discord.HTTPException):
    status = {discord.Forbidden: 403, discord.NotFound: 404}.get(cls, 500)
    return cls(SimpleNamespace(status=status, reason="x"), "boom")


def make_member(uid: int, name: str, bot: bool = False):
    m = MagicMock(spec=discord.Member)
    m.id, m.bot, m.name, m.display_name, m.mention = uid, bot, name, name, f"<@{uid}>"
    m.global_name = None
    m.display_avatar = SimpleNamespace(url=f"https://cdn/{uid}.png")
    m.timeout_for, m.kick = AsyncMock(), AsyncMock()
    return m


def make_user(uid: int, name: str = "outsider"):
    u = MagicMock(spec=discord.User)
    u.id, u.bot, u.name, u.mention = uid, False, name, f"<@{uid}>"
    u.display_avatar = SimpleNamespace(url=f"https://cdn/{uid}.png")
    return u


def make_channel(cid: int, name: str, valid: bool = True):
    c = MagicMock(spec=discord.TextChannel)
    c.id, c.name, c.position, c.type = cid, name, cid, discord.ChannelType.text
    perms = SimpleNamespace(view_channel=valid, send_messages=valid, embed_links=valid, read_message_history=True)
    c.permissions_for = MagicMock(return_value=perms)
    c.send = AsyncMock()
    return c


class FakeGuild(MagicMock):
    pass


def make_guild():
    guild = MagicMock(spec=discord.Guild)
    guild.id = GUILD_ID
    guild.me = make_member(1, "bot")
    guild.by_id = {
        m.id: m
        for m in (make_member(ME, "admin"), make_member(ALICE, "alice"), make_member(BOT_USER, "somebot", bot=True))
    }
    guild.members = list(guild.by_id.values())
    guild.get_member = lambda uid: guild.by_id.get(uid)
    guild.channels = {CHANNEL: make_channel(CHANNEL, "公告"), 701: make_channel(701, "沒權限", valid=False)}
    guild.get_channel = lambda cid: guild.channels.get(cid)
    guild.text_channels = list(guild.channels.values())
    guild.ban, guild.fetch_ban = AsyncMock(), AsyncMock(side_effect=http_error(discord.NotFound))
    return guild


@pytest.fixture
def client(discord_env, repo, dashboard_env, monkeypatch) -> TestClient:  # noqa: F811
    seed_token(repo, dashboard_env.credential_id)
    make_session(repo)
    discord_env.guilds = [g(str(GUILD_ID), "guild", ALL)]
    guild = make_guild()
    bot = fake_bot(guild)
    bot.get_guild = lambda gid: guild if gid == GUILD_ID else None
    bot.get_user = lambda uid: None
    bot.fetch_user = AsyncMock(side_effect=lambda uid: make_user(uid) if uid == STRANGER else _raise_not_found())
    monkeypatch.setattr(warnings, "sqldb", repo)
    monkeypatch.setattr(sclient, "bot", bot)
    monkeypatch.setattr(moderation.sclient, "sqldb", repo, raising=False)
    moderation.register_after_warning(None)
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
    c.cookies.set("dashboard_session", "sid")
    c.repo, c.guild, c.discord_env = repo, guild, discord_env  # pyright: ignore[reportAttributeAccessIssue]
    yield c
    moderation.register_after_warning(None)


def _raise_not_found():
    raise http_error(discord.NotFound)


def records(client) -> list[UserModerate]:
    return client.repo.get_warnings(ALICE, GUILD_ID) + client.repo.get_warnings(STRANGER, GUILD_ID)


def post(client, **body):
    return client.post(URL, json={"reason": "理由", **body}, headers={"Origin": FRONTEND})


class TestPermission:
    @pytest.mark.parametrize(
        ("kind", "bit", "extra"),
        [
            ("warning", MANAGE_MESSAGES, {}),
            ("timeout", MODERATE, {"duration_seconds": 600}),
            ("kick", KICK, {}),
            ("ban", BAN, {}),
        ],
    )
    def test_each_kind_needs_its_own_permission(self, client, kind, bit, extra):
        client.discord_env.guilds = [
            g(str(GUILD_ID), "guild", ALL & ~bit | 0x10)
        ]  # 缺該權限，另給 Manage Guild 以能進入
        response = post(client, kind=kind, user_id=str(ALICE), **extra)
        assert response.status_code == 403
        assert response.json()["error"] == "no_permission"
        assert records(client) == []
        client.discord_env.guilds = [g(str(GUILD_ID), "guild", bit)]
        guilds._cache.clear()
        assert post(client, kind=kind, user_id=str(ALICE), **extra).status_code == 200

    def test_unknown_kind_is_400(self, client):
        response = post(client, kind="nuke", user_id=str(ALICE))
        assert response.status_code == 400
        assert response.json()["fields"][0]["path"] == "kind"


class TestTargets:
    def test_warning_and_ban_accept_user_not_in_guild(self, client):
        assert post(client, kind="warning", user_id=str(STRANGER)).json()["result"]["ok"] is True
        assert post(client, kind="ban", user_id=str(STRANGER)).json()["result"]["ok"] is True
        client.guild.ban.assert_awaited_once()
        assert len(client.repo.get_warnings(STRANGER, GUILD_ID)) == 2

    @pytest.mark.parametrize(("kind", "extra"), [("timeout", {"duration_seconds": 600}), ("kick", {})])
    def test_timeout_and_kick_need_member(self, client, kind, extra):
        response = post(client, kind=kind, user_id=str(STRANGER), **extra)
        assert response.status_code == 400
        assert response.json()["error"] == "not_member"
        assert records(client) == []

    def test_unknown_user_id_is_blocked(self, client):
        response = post(client, kind="warning", user_id="123456789")
        assert response.status_code == 400
        assert response.json()["error"] == "user_not_found"

    @pytest.mark.parametrize("user_id", ["abc", "0", "-5", str(2**64)])
    def test_malformed_id_is_400(self, client, user_id):
        response = post(client, kind="warning", user_id=user_id)
        assert response.status_code == 400
        assert response.json()["fields"][0]["path"] == "user_id"

    @pytest.mark.parametrize("who", [BOT_USER, ME])
    def test_bot_and_self_are_refused(self, client, who):
        body = post(client, kind="warning", user_id=str(who)).json()
        assert body["result"]["ok"] is False
        assert body["result"]["error"] in ("不能對機器人執行", "不能對自己執行")
        assert client.repo.get_warnings(who, GUILD_ID) == []


class TestRecord:
    def test_warning_writes_guild_only_record_with_actor(self, client):
        body = post(client, kind="warning", user_id=str(ALICE), reason="  吵架  ").json()
        row = client.repo.get_warnings(ALICE, GUILD_ID)[0]
        assert body["result"]["warning_id"] == row.warning_id
        assert (row.reason, row.guild_only, row.moderate_user, row.moderate_type) == (
            "吵架",
            True,
            ME,
            WarningType.Warning,
        )

    def test_cross_guild_flag(self, client):
        post(client, kind="warning", user_id=str(ALICE), cross_guild=True)
        assert client.repo.get_warnings(ALICE, GUILD_ID)[0].guild_only is False

    def test_timeout_records_duration_and_deletes_messages(self, client, monkeypatch):
        monkeypatch.setattr(
            moderation,
            "delete_recent_messages",
            AsyncMock(return_value="最近 3600 秒內全伺服器共刪除 3 則（略過 1 個頻道）"),
        )
        body = post(
            client, kind="timeout", user_id=str(ALICE), duration_seconds=600, delete_message_seconds=3600
        ).json()
        assert body["result"]["deleted_summary"] == "最近 3600 秒內全伺服器共刪除 3 則（略過 1 個頻道）"
        client.guild.by_id[ALICE].timeout_for.assert_awaited_once()
        assert client.repo.get_warnings(ALICE, GUILD_ID)[0].last_time.total_seconds() == 600

    def test_audit_reason_prefix(self, client):
        post(client, kind="kick", user_id=str(ALICE), reason="吵")
        reason = client.guild.by_id[ALICE].kick.await_args.kwargs["reason"]
        assert reason.startswith("admin 透過後台：")

    def test_kick_forbidden_shows_error_and_writes_nothing(self, client):
        client.guild.by_id[ALICE].kick.side_effect = http_error(discord.Forbidden)
        body = post(client, kind="kick", user_id=str(ALICE)).json()
        assert body["result"]["ok"] is False
        assert "位階" in body["result"]["error"]
        assert records(client) == []

    def test_ban_already_banned_is_success_without_second_record(self, client):
        assert post(client, kind="ban", user_id=str(ALICE)).json()["result"]["already"] is False
        client.guild.fetch_ban = AsyncMock(return_value=object())
        body = post(client, kind="ban", user_id=str(ALICE)).json()
        assert body["result"]["ok"] is True
        assert body["result"]["already"] is True
        assert client.guild.ban.await_count == 1
        assert len(client.repo.get_warnings(ALICE, GUILD_ID)) == 1

    def test_auto_timeout_result_is_returned(self, client):
        from datetime import timedelta

        async def hook(guild, target, warning_id):
            return moderation.AutoTimeoutResult(ok=True, duration=timedelta(hours=1))

        moderation.register_after_warning(hook)
        body = post(client, kind="warning", user_id=str(ALICE)).json()
        assert body["result"]["auto_timeout"] == {"ok": True, "duration_seconds": 3600, "error": None}


class TestValidation:
    @pytest.mark.parametrize("kind", ["warning", "ban"])
    @pytest.mark.parametrize("reason", [None, "", "   "])
    def test_reason_required(self, client, kind, reason):
        response = client.post(
            URL, json={"kind": kind, "user_id": str(ALICE), "reason": reason}, headers={"Origin": FRONTEND}
        )
        assert response.status_code == 400
        assert response.json()["fields"][0]["path"] == "reason"
        assert records(client) == []

    def test_reason_over_100_chars(self, client):
        assert post(client, kind="warning", user_id=str(ALICE), reason="字" * 101).status_code == 400
        assert post(client, kind="warning", user_id=str(ALICE), reason="字" * 100).status_code == 200

    def test_kick_and_timeout_reason_optional(self, client):
        assert (
            client.post(URL, json={"kind": "kick", "user_id": str(ALICE)}, headers={"Origin": FRONTEND}).status_code
            == 200
        )

    @pytest.mark.parametrize("seconds", [None, 0, 59, 604801])
    def test_timeout_duration_bounds(self, client, seconds):
        response = post(client, kind="timeout", user_id=str(ALICE), duration_seconds=seconds)
        assert response.status_code == 400
        assert response.json()["fields"][0]["path"] == "duration_seconds"

    def test_timeout_duration_edges_ok(self, client):
        assert post(client, kind="timeout", user_id=str(ALICE), duration_seconds=60).status_code == 200
        assert post(client, kind="timeout", user_id=str(ALICE), duration_seconds=604800).status_code == 200

    def test_ban_delete_seconds_must_be_a_choice(self, client):
        assert post(client, kind="ban", user_id=str(ALICE), delete_message_seconds=100).status_code == 400
        assert post(client, kind="ban", user_id=str(ALICE), delete_message_seconds=86400).status_code == 200
        assert client.guild.ban.await_args.kwargs["delete_message_seconds"] == 86400

    def test_timeout_delete_seconds_upper_bound(self, client):
        assert (
            post(
                client, kind="timeout", user_id=str(ALICE), duration_seconds=60, delete_message_seconds=604801
            ).status_code
            == 400
        )


class TestAnnounce:
    def test_no_channel_means_no_announcement(self, client):
        body = post(client, kind="warning", user_id=str(ALICE)).json()
        assert body["announce_error"] is None
        client.guild.channels[CHANNEL].send.assert_not_awaited()

    def test_announces_mention_and_embed_with_id(self, client):
        body = post(client, kind="warning", user_id=str(ALICE), announce_channel_id=str(CHANNEL)).json()
        assert body["announce_error"] is None
        sent = client.guild.channels[CHANNEL].send.await_args.kwargs
        assert sent["content"] == f"<@{ALICE}>"
        assert f"編號：{body['result']['warning_id']}" in sent["embed"].description

    def test_invalid_channel_keeps_record_and_reports(self, client):
        body = post(client, kind="warning", user_id=str(ALICE), announce_channel_id="701").json()
        assert body["result"]["ok"] is True
        assert "bot 缺少" in body["announce_error"]
        assert len(client.repo.get_warnings(ALICE, GUILD_ID)) == 1

    def test_send_failure_keeps_record_and_reports(self, client):
        client.guild.channels[CHANNEL].send.side_effect = http_error(discord.Forbidden)
        body = post(client, kind="warning", user_id=str(ALICE), announce_channel_id=str(CHANNEL)).json()
        assert body["result"]["ok"] is True
        assert body["announce_error"]
        assert len(client.repo.get_warnings(ALICE, GUILD_ID)) == 1

    def test_failed_punish_does_not_announce(self, client):
        client.guild.by_id[ALICE].kick.side_effect = http_error(discord.Forbidden)
        body = post(client, kind="kick", user_id=str(ALICE), announce_channel_id=str(CHANNEL)).json()
        assert body["announce_error"] is None
        client.guild.channels[CHANNEL].send.assert_not_awaited()


class TestOptions:
    def test_lists_only_usable_text_channels(self, client):
        client.discord_env.guilds = [g(str(GUILD_ID), "guild", BAN)]
        body = client.get(f"{URL}/options").json()
        assert body["channels"] == [{"id": str(CHANNEL), "name": "公告"}]

    def test_no_entry_permission_is_403(self, client):
        client.discord_env.guilds = [g(str(GUILD_ID), "guild", 0)]
        assert client.get(f"{URL}/options").status_code == 403


class TestMemberSearchFlagsBots:
    def test_bot_flag(self, client):
        client.guild.by_id[BOT_USER].display_name = "somebot"
        found = client.get(f"{URL}/member-search", params={"q": "some"}).json()["members"]
        assert [(m["id"], m["bot"]) for m in found] == [(str(BOT_USER), True)]
        found = client.get(f"{URL}/member-search", params={"q": "alice"}).json()["members"]
        assert [(m["id"], m["bot"]) for m in found] == [(str(ALICE), False)]
