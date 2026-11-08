"""伺服器管理後台 T-05：範例內容產生器與預覽 API。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from test_dashboard_auth import FRONTEND, dashboard_env, make_app, make_session  # noqa: F401  (fixture 與 helper)
from test_dashboard_guilds import MANAGE_CHANNELS, MANAGE_GUILD, g, seed_token
from test_dashboard_guilds import discord as discord_env  # noqa: F401  (fixture)
from test_dashboard_notifies import GUILD_ID, OK_ROLE, fake_bot, fake_guild
from test_identity import repo  # noqa: F401

from starlib import sclient
from starServer.dashboard.notify_fields import CHANNEL_SPECS, COMMUNITY_SPECS
from starServer.dashboard.samples import SAMPLE_MEMBER_MENTION, SAMPLE_TWEET_URL, build_sample

ROOT = Path(__file__).resolve().parent.parent
GUILD = SimpleNamespace(name="範例伺服器")
ROLE = f"<@&{OK_ROLE}>"
ALL_SPECS = [*CHANNEL_SPECS, *COMMUNITY_SPECS]
NO_CARD = {"channel:7", "channel:8", "community:5"}


def sample(key: str, **values):
    return build_sample(key, values, guild=GUILD)


class TestBuildSample:
    @pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.key)
    def test_every_type_builds(self, spec):
        s = sample(spec.key)
        if spec.key in NO_CARD:
            assert s.embeds == [] and s.content
        else:
            assert s.embeds
            for e in s.embeds:
                e.to_dict()  # 可序列化給網頁

    def test_member_join_and_leave_are_text_only(self):
        join = sample("channel:7", message="歡迎 {member} 來到 {guild}")
        assert join.content == f"歡迎 {SAMPLE_MEMBER_MENTION} 來到 範例伺服器" and join.embeds == []
        leave = sample("channel:8", message="{member} 離開 {guild}")
        assert leave.content == f"{SAMPLE_MEMBER_MENTION} 離開 範例伺服器"

    def test_member_defaults_and_real_member(self):
        assert sample("channel:7").content == f"{SAMPLE_MEMBER_MENTION} (範例成員) 加入了我們"
        assert sample("channel:8").content == f"{SAMPLE_MEMBER_MENTION} (範例成員) 離開了我們"
        m = SimpleNamespace(mention="<@5>", name="bob", discriminator="1234")
        s = build_sample("channel:7", {}, member=m, guild=GUILD)
        assert s.content == "<@5> (bob#1234) 加入了我們"

    def test_twitter_matches_task_py(self):
        s = sample("community:5")
        assert s.embeds == []
        assert s.content == f"範例使用者 發布新推文\n{SAMPLE_TWEET_URL}"
        with_role = sample("community:5", role_id=str(OK_ROLE), message="ignored")
        assert with_role.content == f"{ROLE} 範例使用者 發布新推文\n{SAMPLE_TWEET_URL}"
        assert with_role.mention_role_id == OK_ROLE

    def test_channel_notify_mention_goes_after_text(self):
        s = sample("channel:3", role_id=str(OK_ROLE))  # MajorQuake
        assert s.content == f"顯著有感地震報告 {ROLE}" and s.mention_role_id == OK_ROLE
        assert sample("channel:12", role_id=str(OK_ROLE)).content == f"小區域地震報告 {ROLE}"
        assert sample("channel:3").content == "顯著有感地震報告"

    def test_mention_only_types(self):
        for key in ("channel:1", "channel:2", "channel:11"):
            assert sample(key, role_id=str(OK_ROLE)).content == ROLE
            assert sample(key).content == ""

    def test_community_mention_goes_before_text(self):
        s = sample("community:1", role_id=str(OK_ROLE), message="開台了")
        assert s.content == f"{ROLE} 開台了" and s.embeds
        assert sample("community:4").content == ""
        assert sample("community:4", role_id=str(OK_ROLE)).content == ROLE

    def test_empty_message_uses_default(self):
        assert sample("channel:7", message="").content.endswith("加入了我們")
        assert sample("community:1", message="").content == ""

    @pytest.mark.parametrize(
        ("key", "ignored"),
        [
            ("channel:4", {"role_id": str(OK_ROLE), "message": "x"}),  # 天氣預報：沒有身分組與文字
            ("channel:5", {"role_id": str(OK_ROLE), "message": "x"}),
            ("channel:6", {"role_id": str(OK_ROLE), "message": "x"}),
            ("channel:1", {"message": "x"}),
            ("channel:7", {"role_id": str(OK_ROLE)}),
            ("community:5", {"message": "x"}),
        ],
    )
    def test_only_checked_fields_are_used(self, key, ignored):
        assert sample(key, **ignored).content == sample(key).content
        assert sample(key, **ignored).mention_role_id is None

    def test_forecast_default_text(self):
        assert sample("channel:4").content == "6小時天氣預報"

    def test_invalid_input(self):
        with pytest.raises(KeyError):
            sample("channel:9")
        with pytest.raises(ValueError):
            sample("channel:1", role_id="abc")

    @pytest.mark.parametrize(
        ("path", "text"),
        [
            ("starDiscord/cmds/task.py", "顯著有感地震報告"),
            ("starDiscord/cmds/task.py", "小區域地震報告"),
            ("starDiscord/cmds/task.py", "6小時天氣預報"),
            ("starDiscord/cmds/task.py", "發布新推文"),
            ("starDiscord/cmds/bot_event.py", "加入了我們"),
            ("starDiscord/cmds/bot_event.py", "離開了我們"),
            (
                "starDiscord/cmds/bot_event.py",
                '.replace("{member}", member.mention).replace("{guild}", member.guild.name)',
            ),
            ("starDiscord/bot.py", 'f"{default_content} {role.mention}"'),
            ("starDiscord/bot.py", 'f"{role.mention} {text}"'),
        ],
    )
    def test_defaults_still_match_senders(self, path, text):
        assert text in (ROOT / path).read_text(encoding="utf-8")


class TestPreviewEndpoint:
    @pytest.fixture
    def client(self, discord_env, repo, dashboard_env, monkeypatch) -> TestClient:  # noqa: F811
        seed_token(repo, dashboard_env.credential_id)
        make_session(repo)
        discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_CHANNELS)]
        monkeypatch.setattr(sclient, "bot", fake_bot(fake_guild()))
        c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
        c.cookies.set("dashboard_session", "sid")
        return c

    def post(self, client: TestClient, body: dict):
        return client.post(f"/dashboard/guilds/{GUILD_ID}/preview", json=body, headers={"Origin": FRONTEND})

    def test_channel_notify(self, client):
        res = self.post(client, {"notify_type": "channel:3", "values": {"role_id": str(OK_ROLE)}})
        body = res.json()
        assert res.status_code == 200
        assert body["content"] == f"顯著有感地震報告 {ROLE}"
        assert body["mention_role_id"] == str(OK_ROLE) and body["mention_role_name"] == "ping"
        assert body["embeds"][0]["title"] == "地震報告"

    def test_unknown_role_has_no_name(self, client):
        body = self.post(client, {"notify_type": "channel:1", "values": {"role_id": "999"}}).json()
        assert body["mention_role_id"] == "999" and body["mention_role_name"] is None

    @pytest.mark.parametrize(
        "body",
        [
            {"notify_type": "channel:9"},
            {"notify_type": "channel:1", "values": {"role_id": "abc"}},
            {"values": {}},
        ],
    )
    def test_invalid(self, client, body):
        res = self.post(client, body)
        assert (res.status_code, res.json()) == (400, {"error": "invalid_request"})

    def test_no_permission(self, client, discord_env):
        discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_GUILD)]
        res = self.post(client, {"notify_type": "channel:1"})
        assert (res.status_code, res.json()) == (403, {"error": "no_permission"})

    def test_bot_not_in_guild(self, client, monkeypatch):
        monkeypatch.setattr(sclient, "bot", fake_bot(None))
        res = self.post(client, {"notify_type": "channel:1"})
        assert (res.status_code, res.json()) == (404, {"error": "bot_not_in_guild"})
