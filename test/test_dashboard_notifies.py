"""伺服器管理後台 T-03：欄位對照、有效性判斷、存取檢查與通知一覽（假 Discord，真實 PostgreSQL）。"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import discord
import pytest
from fastapi.testclient import TestClient
from test_dashboard_auth import dashboard_env, make_app, make_session  # noqa: F401  (fixture 與 helper)
from test_dashboard_guilds import MANAGE_CHANNELS, MANAGE_GUILD, g, seed_token  # noqa: F401
from test_identity import repo  # noqa: F401

from starlib import sclient
from starlib.database import (
    Community,
    NotifyChannel,
    NotifyChannelType,
    NotifyCommunity,
    NotifyCommunityType,
    PlatformType,
)
from starServer.dashboard import notifies
from starServer.dashboard.notify_fields import CHANNEL_SPECS, COMMUNITY_SPECS, channel_spec, parse_key
from starServer.dashboard.validity import channel_invalid_reason, role_invalid_reason

GUILD_ID = 1001
OK_CHANNEL = 11
VOICE_CHANNEL = 12
NO_SEND_CHANNEL = 13
NO_HISTORY_CHANNEL = 14
OK_ROLE = 21
LOCKED_ROLE = 22
MANAGED_ROLE = 23


def perms(**missing: bool) -> SimpleNamespace:
    values = dict(view_channel=True, send_messages=True, embed_links=True, read_message_history=True)
    values.update({k: False for k in missing})
    return SimpleNamespace(**values)


def channel(cid: int, name: str, type=discord.ChannelType.text, **missing) -> SimpleNamespace:
    p = perms(**missing)
    return SimpleNamespace(id=cid, name=name, type=type, permissions_for=lambda _me: p)


def role(rid: int, name: str, *, mentionable=True, managed=False, default=False) -> SimpleNamespace:
    return SimpleNamespace(id=rid, name=name, mentionable=mentionable, managed=managed, is_default=lambda: default)


def fake_guild(mention_everyone: bool = False) -> SimpleNamespace:
    channels = {
        c.id: c
        for c in (
            channel(OK_CHANNEL, "general"),
            channel(VOICE_CHANNEL, "voice", discord.ChannelType.voice),
            channel(NO_SEND_CHANNEL, "locked", send_messages=True),
            channel(NO_HISTORY_CHANNEL, "nohistory", read_message_history=True),
            channel(15, "news", discord.ChannelType.news),
        )
    }
    roles = {
        r.id: r
        for r in (
            role(OK_ROLE, "ping"),
            role(LOCKED_ROLE, "locked", mentionable=False),
            role(MANAGED_ROLE, "bot-role", managed=True),
            role(GUILD_ID, "@everyone", default=True),
        )
    }
    me = SimpleNamespace(guild_permissions=SimpleNamespace(mention_everyone=mention_everyone))
    return SimpleNamespace(id=GUILD_ID, me=me, get_channel=channels.get, get_role=roles.get)


class TestValidity:
    def test_channel(self):
        guild = fake_guild()
        assert channel_invalid_reason(guild, OK_CHANNEL, False) is None
        assert channel_invalid_reason(guild, 15, False) is None  # 公告頻道
        assert channel_invalid_reason(guild, 999, False) == "頻道不存在"
        assert channel_invalid_reason(guild, VOICE_CHANNEL, False) == "不支援的頻道類型"
        assert channel_invalid_reason(guild, NO_SEND_CHANNEL, False) == "bot 缺少 Send Messages"

    def test_scheduled_needs_read_history(self):
        guild = fake_guild()
        assert channel_invalid_reason(guild, NO_HISTORY_CHANNEL, False) is None
        assert channel_invalid_reason(guild, NO_HISTORY_CHANNEL, True) == "bot 缺少 Read Message History"

    def test_role(self):
        guild = fake_guild()
        assert role_invalid_reason(guild, OK_ROLE) is None
        assert role_invalid_reason(guild, 999) == "身分組不存在"
        assert role_invalid_reason(guild, GUILD_ID) == "@everyone 不能使用"
        assert role_invalid_reason(guild, MANAGED_ROLE) is not None
        assert role_invalid_reason(guild, LOCKED_ROLE) is not None

    def test_unmentionable_role_ok_with_mention_everyone(self):
        assert role_invalid_reason(fake_guild(mention_everyone=True), LOCKED_ROLE) is None


class TestNotifyFields:
    def test_twelve_channel_types_without_deprecated(self):
        assert len(CHANNEL_SPECS) == 12
        assert len(COMMUNITY_SPECS) == 5
        assert channel_spec(9) is None  # DynamicVoice 已廢棄
        with pytest.raises(KeyError):
            parse_key("channel:9")
        with pytest.raises(KeyError):
            parse_key("4")

    def test_keys_do_not_collide(self):
        assert parse_key("channel:4").kind == "channel"
        assert parse_key("community:4").kind == "community"
        assert parse_key("channel:4").name != parse_key("community:4").name

    @pytest.mark.parametrize(
        ("key", "role", "message", "scheduled"),
        [
            ("channel:1", True, False, False),  # 全群公告
            ("channel:2", True, False, False),  # 機器人更新
            ("channel:3", True, False, False),  # 重大地震
            ("channel:12", True, False, False),  # 小規模地震
            ("channel:11", True, False, False),  # 天氣警報
            ("channel:4", False, False, True),  # 天氣預報
            ("channel:5", False, False, True),  # Apex 輪替
            ("channel:7", False, True, False),  # 成員加入
            ("channel:8", False, True, False),  # 成員離開
            ("channel:6", False, False, False),  # 加入紀錄
            ("channel:13", False, False, False),  # 離開紀錄
            ("channel:10", False, False, False),  # 語音紀錄
            ("community:1", True, True, False),  # Twitch 開台
            ("community:3", True, True, False),  # Twitch 影片
            ("community:4", True, True, False),  # Twitch 剪輯
            ("community:2", True, True, False),  # YouTube
            ("community:5", True, False, False),  # Twitter
        ],
    )
    def test_field_table(self, key, role, message, scheduled):
        spec = parse_key(key)
        assert (spec.has_role, spec.has_message, spec.scheduled) == (role, message, scheduled)

    def test_names(self):
        assert parse_key("channel:1").name == "全群公告"
        assert parse_key("channel:4").name == "台灣各縣市天氣預報"
        assert parse_key("community:1").name == "Twitch 開台通知"
        assert parse_key("community:2").name == "YouTube"
        assert parse_key("community:5").name == "Twitter"


def fake_bot(guild=None, ready: bool = True):
    pool = ThreadPoolExecutor(max_workers=1)
    return SimpleNamespace(
        is_ready=lambda: ready,
        get_guild=lambda gid: guild if gid == GUILD_ID else None,
        submit=lambda coro: pool.submit(asyncio.run, coro),
    )


# ====== GET /dashboard/guilds/{id}/notifies ======
class TestNotifiesEndpoint:
    @pytest.fixture
    def client(self, discord_env, repo, dashboard_env, monkeypatch) -> TestClient:  # noqa: F811
        seed_token(repo, dashboard_env.credential_id)
        make_session(repo)
        discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_CHANNELS)]
        monkeypatch.setattr(notifies, "sqldb", repo)
        monkeypatch.setattr(sclient, "bot", fake_bot(fake_guild()))
        c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
        c.cookies.set("dashboard_session", "sid")
        return c

    def get(self, client: TestClient):
        return client.get(f"/dashboard/guilds/{GUILD_ID}/notifies")

    def test_empty(self, client):
        assert self.get(client).json() == {"channel_notifies": [], "community_notifies": []}

    def test_channel_notifies_show_only_used_fields(self, client, repo):  # noqa: F811
        repo.add(
            NotifyChannel(
                guild_id=GUILD_ID,
                notify_type=NotifyChannelType.WeatherForecast,
                channel_id=OK_CHANNEL,
                role_id=OK_ROLE,
                message="x",
            )
        )
        repo.add(
            NotifyChannel(
                guild_id=GUILD_ID,
                notify_type=NotifyChannelType.MemberJoin,
                channel_id=OK_CHANNEL,
                role_id=OK_ROLE,
                message="hi {member}",
            )
        )
        repo.add(
            NotifyChannel(
                guild_id=GUILD_ID,
                notify_type=NotifyChannelType.AllAnnouncements,
                channel_id=OK_CHANNEL,
                role_id=OK_ROLE,
                message="x",
            )
        )
        items = {i["key"]: i for i in self.get(client).json()["channel_notifies"]}
        forecast = items["channel:4"]
        assert "role" not in forecast and "message" not in forecast
        assert forecast["values"] == {"channel_id": str(OK_CHANNEL)}
        join = items["channel:7"]
        assert join["message"] == "hi {member}" and "role" not in join
        assert join["values"] == {"channel_id": str(OK_CHANNEL), "message": "hi {member}"}
        announce = items["channel:1"]
        assert announce["role"] == {"id": str(OK_ROLE), "name": "ping", "invalid": None}
        assert announce["channel"] == {"id": str(OK_CHANNEL), "name": "general", "invalid": None}
        assert "message" not in announce
        assert announce["values"] == {"channel_id": str(OK_CHANNEL), "role_id": str(OK_ROLE)}

    def test_invalid_channel_and_role_are_marked(self, client, repo):  # noqa: F811
        repo.add(
            NotifyChannel(
                guild_id=GUILD_ID,
                notify_type=NotifyChannelType.AllAnnouncements,
                channel_id=NO_SEND_CHANNEL,
                role_id=LOCKED_ROLE,
            )
        )
        repo.add(
            NotifyChannel(guild_id=GUILD_ID, notify_type=NotifyChannelType.BotUpdates, channel_id=999, role_id=None)
        )
        # 天氣預報：定時通知，缺 Read Message History 才算失效
        repo.add(
            NotifyChannel(
                guild_id=GUILD_ID, notify_type=NotifyChannelType.WeatherForecast, channel_id=NO_HISTORY_CHANNEL
            )
        )
        repo.add(NotifyChannel(guild_id=GUILD_ID, notify_type=NotifyChannelType.JoinLog, channel_id=NO_HISTORY_CHANNEL))
        items = {i["key"]: i for i in self.get(client).json()["channel_notifies"]}
        assert items["channel:1"]["channel"]["invalid"] == "bot 缺少 Send Messages"
        assert items["channel:1"]["role"]["invalid"] is not None
        assert items["channel:2"]["channel"] == {"id": "999", "name": None, "invalid": "頻道不存在"}
        assert items["channel:2"]["role"] is None
        assert items["channel:4"]["channel"]["invalid"] == "bot 缺少 Read Message History"
        assert items["channel:6"]["channel"]["invalid"] is None

    def test_deprecated_type_is_skipped(self, client, repo):  # noqa: F811
        repo.add(NotifyChannel(guild_id=GUILD_ID, notify_type=9, channel_id=OK_CHANNEL))  # pyright: ignore[reportArgumentType]
        assert self.get(client).json()["channel_notifies"] == []

    def test_other_guild_not_listed(self, client, repo):  # noqa: F811
        repo.add(NotifyChannel(guild_id=GUILD_ID + 1, notify_type=NotifyChannelType.JoinLog, channel_id=OK_CHANNEL))
        assert self.get(client).json()["channel_notifies"] == []

    def test_community_notifies(self, client, repo):  # noqa: F811
        repo.add(Community(id="u1", type=PlatformType.Twitch, username="login1", display_name="Display One"))
        repo.add(Community(id="u2", type=PlatformType.Twitch, username="login2", display_name=None))
        repo.add(Community(id="UCabc", type=PlatformType.Google, username="@handle", display_name="Yt"))
        for t, cid, ptype in (
            (NotifyCommunityType.TwitchLive, "u1", PlatformType.Twitch),
            (NotifyCommunityType.TwitchClip, "u1", PlatformType.Twitch),
            (NotifyCommunityType.TwitchLive, "u2", PlatformType.Twitch),
            (NotifyCommunityType.Youtube, "UCabc", PlatformType.Google),
            # 孤兒列：沒有對應的 Community（例如沒有 handle 的 YouTube 頻道）
            (NotifyCommunityType.Youtube, "UCorphan", PlatformType.Google),
        ):
            repo.add(
                NotifyCommunity(
                    notify_type=t,
                    community_id=cid,
                    community_type=ptype,
                    guild_id=GUILD_ID,
                    channel_id=OK_CHANNEL,
                    role_id=OK_ROLE,
                    message="m",
                )
            )
        data = self.get(client).json()["community_notifies"]
        assert [(i["key"], i["account"]["id"]) for i in data] == [
            ("community:1", "u1"),
            ("community:1", "u2"),
            ("community:4", "u1"),
            ("community:2", "UCorphan"),
            ("community:2", "UCabc"),
        ]
        assert data[0]["account"] == {"id": "u1", "display_name": "Display One", "username": "login1"}
        assert data[1]["account"] == {"id": "u2", "display_name": "login2", "username": "login2"}
        assert data[3]["account"] == {"id": "UCorphan", "display_name": "UCorphan", "username": "UCorphan"}
        assert data[3]["role"]["id"] == str(OK_ROLE) and data[4]["message"] == "m"

    def test_twitter_has_no_message(self, client, repo):  # noqa: F811
        repo.add(Community(id="t1", type=PlatformType.Twitter, username="tw", display_name="Tw"))
        repo.add(
            NotifyCommunity(
                notify_type=NotifyCommunityType.TwitterTweet,
                community_id="t1",
                community_type=PlatformType.Twitter,
                guild_id=GUILD_ID,
                channel_id=OK_CHANNEL,
                message="stale",
            )
        )
        item = self.get(client).json()["community_notifies"][0]
        assert "message" not in item and item["role"] is None
        assert item["values"] == {"channel_id": str(OK_CHANNEL), "role_id": None}

    def test_no_permission(self, client, discord_env):
        discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_GUILD)]
        res = self.get(client)
        assert (res.status_code, res.json()) == (403, {"error": "no_permission"})

    def test_user_not_in_guild(self, client, discord_env):
        discord_env.guilds = []
        assert self.get(client).json() == {"error": "no_permission"}

    def test_bot_not_in_guild(self, client, monkeypatch):
        monkeypatch.setattr(sclient, "bot", fake_bot(None))
        res = self.get(client)
        assert (res.status_code, res.json()) == (404, {"error": "bot_not_in_guild"})

    @pytest.mark.parametrize("bot", [None, fake_bot(None, ready=False)])
    def test_bot_unavailable(self, client, monkeypatch, bot):
        monkeypatch.setattr(sclient, "bot", bot)
        res = self.get(client)
        assert (res.status_code, res.json()) == (503, {"error": "bot_unavailable"})

    def test_requires_session(self):
        c = TestClient(make_app(), base_url="https://testserver")
        assert c.get(f"/dashboard/guilds/{GUILD_ID}/notifies").json() == {"error": "session_expired"}
