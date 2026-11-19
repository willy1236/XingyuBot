"""動態語音後台 T-01：大廳一覽。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.dynamic_voice.dashboard_helpers import (
    LOBBY,
    NO_CATEGORY_LOBBY,
    OTHER_LOBBY,
    STAGE_CHANNEL,
    TEXT_CHANNEL,
    URL,
    client,  # noqa: F401  (fixture)
    fake_voice_guild,
    use_guild,
)
from tests.helpers.dashboard_auth import make_app
from tests.helpers.dashboard_guilds import g
from tests.helpers.dashboard_notifies import GUILD_ID

pytestmark = pytest.mark.usefixtures("dashboard_env")


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
