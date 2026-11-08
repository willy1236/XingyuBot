"""伺服器管理後台 T-08：測試通知的發送、冷卻與一覽的冷卻欄位。"""

from __future__ import annotations

import time
from types import SimpleNamespace

import discord
import pytest
from fastapi.testclient import TestClient
from test_dashboard_auth import FRONTEND, USER_ID, dashboard_env, make_app, make_session  # noqa: F401  (fixture 與 helper)
from test_dashboard_guilds import MANAGE_CHANNELS, g, seed_token
from test_dashboard_guilds import discord as discord_env  # noqa: F401  (fixture)
from test_dashboard_notifies import GUILD_ID, NO_SEND_CHANNEL, OK_CHANNEL, OK_ROLE, fake_bot, fake_guild
from test_identity import repo  # noqa: F401

from starlib import sclient
from starlib.database import Community, NotifyCommunity, PlatformType
from starlib.database import NotifyChannelType as T
from starlib.database import NotifyCommunityType as C
from starServer.dashboard import notifies, notify_cooldown, test_notify


class Sent:
    def __init__(self):
        self.calls: list[tuple[str, list, discord.AllowedMentions]] = []
        self.error: Exception | None = None

    async def send(self, content, *, embeds, allowed_mentions):
        if self.error is not None:
            raise self.error
        self.calls.append((content, embeds, allowed_mentions))


@pytest.fixture(autouse=True)
def clean_cooldown():
    notify_cooldown._state.clear()
    yield
    notify_cooldown._state.clear()


class TestCooldown:
    def test_acquire_commit_release(self):
        notify_cooldown.acquire("k")
        assert notify_cooldown.remaining("k") == notify_cooldown.PENDING_RETRY_SECONDS
        notify_cooldown.release("k")  # 失敗：不計入冷卻
        assert notify_cooldown.remaining("k") == 0
        notify_cooldown.acquire("k")
        notify_cooldown.commit("k")
        assert 59 <= notify_cooldown.remaining("k") <= 60

    def test_expires(self):
        notify_cooldown._state["k"] = time.monotonic() - notify_cooldown.COOLDOWN_SECONDS - 1
        assert notify_cooldown.remaining("k") == 0
        assert "k" not in notify_cooldown._state


class TestEndpoint:
    @pytest.fixture
    def sent(self) -> Sent:
        return Sent()

    @pytest.fixture
    def client(self, discord_env, repo, dashboard_env, monkeypatch, sent) -> TestClient:  # noqa: F811
        seed_token(repo, dashboard_env.credential_id)
        make_session(repo)
        discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_CHANNELS)]
        for mod in (test_notify, notifies):
            monkeypatch.setattr(mod, "sqldb", repo)
        guild = fake_guild()
        guild.name = "測試伺服器"
        guild.get_member = lambda uid: None
        member = SimpleNamespace(mention=f"<@{USER_ID}>", name="tester", discriminator="0", display_name="tester")

        async def fetch_member(uid):
            if uid == int(USER_ID):
                return member
            raise discord.HTTPException(SimpleNamespace(status=404, reason="x"), "unknown member")

        guild.fetch_member = fetch_member
        for cid in (OK_CHANNEL, NO_SEND_CHANNEL, 15):
            guild.get_channel(cid).send = sent.send
        monkeypatch.setattr(sclient, "bot", fake_bot(guild))
        c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
        c.cookies.set("dashboard_session", "sid")
        c.repo = repo  # pyright: ignore[reportAttributeAccessIssue]
        return c

    def post(self, client, **body):
        return client.post(f"/dashboard/guilds/{GUILD_ID}/notifies/test", json=body, headers={"Origin": FRONTEND})

    def test_channel_sends_marked_message_without_pinging(self, client, sent):
        client.repo.add_notify_channel(GUILD_ID, T.MajorQuakeNotifications, OK_CHANNEL, OK_ROLE)
        res = self.post(client, kind="channel", notify_type="channel:3")
        assert res.status_code == 200
        content, embeds, mentions = sent.calls[0]
        assert content == f"{test_notify.TEST_LABEL}\n顯著有感地震報告 <@&{OK_ROLE}>"
        assert len(embeds) == 1
        assert mentions.everyone is False and mentions.roles is False and mentions.users is False

    def test_member_placeholder_uses_presser(self, client, sent):
        client.repo.add_notify_channel(GUILD_ID, T.MemberJoin, OK_CHANNEL, None, "歡迎 {member}")
        assert self.post(client, kind="channel", notify_type="channel:7").status_code == 200
        assert sent.calls[0][0] == f"{test_notify.TEST_LABEL}\n歡迎 <@{USER_ID}>"

    def test_uses_saved_settings_not_ignored_columns(self, client, sent):
        # 公告類沒有自訂文字欄位：資料庫存了也不使用
        client.repo.add_notify_channel(GUILD_ID, T.AllAnnouncements, OK_CHANNEL, None, "ignored")
        self.post(client, kind="channel", notify_type="channel:1")
        assert "ignored" not in sent.calls[0][0]

    def test_log_type_only_marker_and_embed(self, client, sent):
        client.repo.add_notify_channel(GUILD_ID, T.JoinLog, OK_CHANNEL)
        self.post(client, kind="channel", notify_type="channel:6")
        content, embeds, _ = sent.calls[0]
        assert content == test_notify.TEST_LABEL and len(embeds) == 1

    def test_community(self, client, sent):
        client.repo.add(Community(id="t1", type=PlatformType.Twitter, username="tw", display_name="Tw"))
        client.repo.add(
            NotifyCommunity(
                notify_type=C.TwitterTweet,
                community_id="t1",
                community_type=PlatformType.Twitter,
                guild_id=GUILD_ID,
                channel_id=OK_CHANNEL,
                role_id=OK_ROLE,
            )
        )
        res = self.post(client, kind="community", notify_type="community:5", account_id="t1")
        assert res.status_code == 200
        assert sent.calls[0][0].startswith(f"{test_notify.TEST_LABEL}\n<@&{OK_ROLE}> ")

    def test_scheduled_rejected(self, client, sent):
        client.repo.add_notify_channel(GUILD_ID, T.WeatherForecast, OK_CHANNEL)
        res = self.post(client, kind="channel", notify_type="channel:4")
        assert (res.status_code, res.json()) == (400, {"error": "scheduled_not_testable"})
        assert sent.calls == []

    def test_not_configured_is_conflict_deleted(self, client):
        res = self.post(client, kind="channel", notify_type="channel:1")
        assert res.status_code == 409 and res.json()["deleted"] is True

    @pytest.mark.parametrize(
        "body",
        [
            {"kind": "channel", "notify_type": "bogus"},
            {"kind": "community", "notify_type": "channel:1"},
            {"kind": "community", "notify_type": "community:1"},  # 缺 account_id
            {"kind": "bad", "notify_type": "channel:1"},
        ],
    )
    def test_invalid_request(self, client, body):
        assert self.post(client, **body).json()["error"] == "invalid_request"

    def test_cooldown_blocks_second_press_and_shows_in_list(self, client, sent):
        client.repo.add_notify_channel(GUILD_ID, T.JoinLog, OK_CHANNEL)
        assert self.post(client, kind="channel", notify_type="channel:6").status_code == 200
        res = self.post(client, kind="channel", notify_type="channel:6")
        assert res.status_code == 429
        assert res.json()["error"] == "cooldown" and 1 <= res.json()["retry_after"] <= 60
        assert len(sent.calls) == 1
        items = client.get(f"/dashboard/guilds/{GUILD_ID}/notifies").json()["channel_notifies"]
        assert items[0]["testable"] is True and 1 <= items[0]["cooldown"] <= 60

    def test_cooldown_is_per_notify(self, client, sent):
        client.repo.add_notify_channel(GUILD_ID, T.JoinLog, OK_CHANNEL)
        client.repo.add_notify_channel(GUILD_ID, T.LeaveLog, OK_CHANNEL)
        assert self.post(client, kind="channel", notify_type="channel:6").status_code == 200
        assert self.post(client, kind="channel", notify_type="channel:13").status_code == 200

    def test_forbidden_reports_reason_and_not_counted(self, client, sent):
        client.repo.add_notify_channel(GUILD_ID, T.JoinLog, OK_CHANNEL)
        sent.error = discord.Forbidden(SimpleNamespace(status=403, reason="x"), "missing")
        res = self.post(client, kind="channel", notify_type="channel:6")
        assert (res.status_code, res.json()["error"]) == (502, "send_failed")
        assert res.json()["reason"]
        sent.error = None
        assert self.post(client, kind="channel", notify_type="channel:6").status_code == 200  # 可立刻再按

    def test_invalid_channel_reported_before_sending(self, client, sent):
        client.repo.add_notify_channel(GUILD_ID, T.JoinLog, NO_SEND_CHANNEL)
        res = self.post(client, kind="channel", notify_type="channel:6")
        assert res.status_code == 502 and "Send Messages" in res.json()["reason"]
        assert notify_cooldown.remaining(notify_cooldown.cooldown_key(GUILD_ID, "channel:6", None)) == 0

    def test_list_scheduled_not_testable(self, client):
        client.repo.add_notify_channel(GUILD_ID, T.WeatherForecast, OK_CHANNEL)
        item = client.get(f"/dashboard/guilds/{GUILD_ID}/notifies").json()["channel_notifies"][0]
        assert item["testable"] is False and item["cooldown"] == 0

    def test_bot_not_in_guild(self, client, monkeypatch):
        client.repo.add_notify_channel(GUILD_ID, T.JoinLog, OK_CHANNEL)
        monkeypatch.setattr(sclient, "bot", fake_bot(None))
        res = self.post(client, kind="channel", notify_type="channel:6")
        assert (res.status_code, res.json()["error"]) == (404, "bot_not_in_guild")

    def test_requires_origin(self, client):
        res = client.post(f"/dashboard/guilds/{GUILD_ID}/notifies/test", json={"kind": "channel", "notify_type": "channel:1"})
        assert res.status_code == 400
