"""動態語音後台 T-01：大廳一覽。"""

from __future__ import annotations

from types import SimpleNamespace

import discord
import pytest
from fastapi.testclient import TestClient
from test_dashboard_auth import FRONTEND, dashboard_env, make_app, make_session  # noqa: F401  (fixture 與 helper)
from test_dashboard_guilds import MANAGE_CHANNELS, g, seed_token
from test_dashboard_guilds import discord as discord_env  # noqa: F401  (fixture)
from test_dashboard_notifies import GUILD_ID, fake_bot
from test_identity import repo  # noqa: F401

from starlib import sclient
from starServer.dashboard import dynamic_voice

LOBBY = 31
OTHER_LOBBY = 32
TEXT_CHANNEL = 33
STAGE_CHANNEL = 34
NO_CATEGORY_LOBBY = 35


def perms(**missing: bool) -> SimpleNamespace:
    values = dict(manage_channels=True, manage_roles=True, move_members=True, send_messages=True, view_channel=True)
    values.update({k: False for k in missing})
    return SimpleNamespace(**values)


def vchannel(cid, name, *, type=discord.ChannelType.voice, category="遊戲", missing=(), position=0):
    p = perms(**dict.fromkeys(missing, True))
    cat = SimpleNamespace(name=category, permissions_for=lambda _me: perms()) if category else None
    return SimpleNamespace(id=cid, name=name, type=type, category=cat, position=position, permissions_for=lambda _me: p)


def fake_voice_guild(*, guild_missing=(), **channel_missing) -> SimpleNamespace:
    chans = [
        vchannel(LOBBY, "大廳", missing=channel_missing.get("lobby", ())),
        vchannel(OTHER_LOBBY, "另一個大廳", position=1),
        vchannel(TEXT_CHANNEL, "文字", type=discord.ChannelType.text),
        vchannel(STAGE_CHANNEL, "舞台", type=discord.ChannelType.stage_voice),
        vchannel(NO_CATEGORY_LOBBY, "最上層", category=None, position=2),
    ]
    by_id = {c.id: c for c in chans}
    me = SimpleNamespace(guild_permissions=perms(**dict.fromkeys(guild_missing, True)))
    guild = SimpleNamespace(
        id=GUILD_ID,
        me=me,
        get_channel=by_id.get,
        voice_channels=[c for c in chans if c.type == discord.ChannelType.voice],
        get_member=lambda _uid: SimpleNamespace(name="willy"),
    )
    for c in chans:
        c.guild = guild
    return guild


@pytest.fixture
def client(discord_env, repo, dashboard_env, monkeypatch) -> TestClient:  # noqa: F811
    seed_token(repo, dashboard_env.credential_id)
    make_session(repo)
    discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_CHANNELS)]
    monkeypatch.setattr(dynamic_voice, "sqldb", repo)
    monkeypatch.setattr(sclient, "bot", fake_bot(fake_voice_guild()))
    repo.cache.dynamic_voice_lobby.load({})
    repo.cache.dynamic_voice_room.load([])
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
    c.cookies.set("dashboard_session", "sid")
    c.repo = repo  # pyright: ignore[reportAttributeAccessIssue]
    c.discord_env = discord_env  # pyright: ignore[reportAttributeAccessIssue]
    return c


def use_guild(monkeypatch, guild):
    monkeypatch.setattr(sclient, "bot", fake_bot(guild))


URL = f"/dashboard/guilds/{GUILD_ID}/dynamic-voice"


class TestGetLobby:
    def test_not_configured(self, client):
        res = client.get(URL)
        assert (res.status_code, res.json()) == (200, {"lobby": None})

    def test_configured(self, client):
        client.repo.add_dynamic_voice_lobby(GUILD_ID, LOBBY, "{member} 的房間")
        assert client.get(URL).json() == {
            "lobby": {
                "channel": {"id": str(LOBBY), "name": "大廳", "category": "遊戲", "invalid": None},
                "template": "{member} 的房間",
                "template_invalid": None,
                "permission_issues": [],
            }
        }

    def test_no_category_shows_null_category(self, client):
        client.repo.add_dynamic_voice_lobby(GUILD_ID, NO_CATEGORY_LOBBY)
        lobby = client.get(URL).json()["lobby"]
        assert lobby["channel"]["category"] is None
        assert lobby["template"] is None

    def test_permission_issues(self, client, monkeypatch):
        use_guild(monkeypatch, fake_voice_guild(lobby=["move_members"]))
        client.repo.add_dynamic_voice_lobby(GUILD_ID, LOBBY)
        assert client.get(URL).json()["lobby"]["permission_issues"] == [
            {"permission": "Move Members", "scope": "channel", "consequence": "無法把進入大廳的人移進房間"}
        ]

    def test_missing_channel_is_invalid(self, client):
        client.repo.add_dynamic_voice_lobby(GUILD_ID, 999)
        lobby = client.get(URL).json()["lobby"]
        assert lobby["channel"] == {"id": "999", "name": None, "category": None, "invalid": "頻道不存在"}
        assert lobby["permission_issues"] == []

    @pytest.mark.parametrize("cid", [TEXT_CHANNEL, STAGE_CHANNEL])
    def test_unsupported_type_is_invalid(self, client, cid):
        client.repo.add_dynamic_voice_lobby(GUILD_ID, cid)
        lobby = client.get(URL).json()["lobby"]
        assert lobby["channel"]["invalid"] == "不支援的頻道類型"
        assert lobby["permission_issues"] == []

    def test_too_long_template_is_invalid_and_returned_raw(self, client):
        template = "  {member}" + "x" * 69 + "  "
        client.repo.add_dynamic_voice_lobby(GUILD_ID, LOBBY, template)
        lobby = client.get(URL).json()["lobby"]
        assert lobby["template_invalid"] == "超過 100 個字元的上限"
        assert lobby["template"] == template  # 原始值，不正規化

    def test_reads_fresh_value(self, client):
        client.repo.add_dynamic_voice_lobby(GUILD_ID, LOBBY, "a")
        client.get(URL)
        client.repo.add_dynamic_voice_lobby(GUILD_ID, OTHER_LOBBY, "b")
        assert client.get(URL).json()["lobby"]["channel"]["id"] == str(OTHER_LOBBY)

    def test_requires_manage_channels(self, client):
        client.discord_env.guilds = [g(str(GUILD_ID), "guild", 0)]
        res = client.get(URL)
        assert (res.status_code, res.json()) == (403, {"error": "no_permission"})

    def test_bot_not_in_guild(self, client, monkeypatch):
        use_guild(monkeypatch, None)
        assert client.get(URL).status_code == 404

    def test_requires_session(self):
        c = TestClient(make_app(), base_url="https://testserver")
        assert c.get(URL).json() == {"error": "session_expired"}
