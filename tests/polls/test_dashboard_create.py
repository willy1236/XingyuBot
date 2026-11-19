"""伺服器管理後台 V-03：後台發起投票（假 Discord，真實 PostgreSQL）。"""

from __future__ import annotations

from types import SimpleNamespace

import discord
import pytest

from tests.helpers.dashboard_guilds import MANAGE_CHANNELS, g
from tests.helpers.dashboard_notifies import GUILD_ID
from tests.polls.create_helpers import (
    OPERATOR,
    URL,
    client,  # noqa: F401  (fixture)
    poll_count,
    post,
)

pytestmark = pytest.mark.usefixtures("dashboard_env")


class TestOptions:
    def test_channels_and_roles(self, client):
        data = client.get(f"{URL}/options").json()
        assert [(c["id"], c["type"], c["disabled_reason"]) for c in data["channels"]] == [
            ("500", "text", None),
            ("501", "news", None),
            ("502", "text", "星羽在這個頻道不能發言"),
            ("503", "text", "你在這個頻道不能發言"),
        ]
        assert [r["id"] for r in data["roles"]] == ["602", "600"]
        assert data["roles"][0] == {"id": "602", "name": "VIP", "color": 0xFF0000}

    def test_needs_manage_messages(self, client):
        client.discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_CHANNELS)]
        assert client.get(f"{URL}/options").status_code == 403

    def test_operator_not_in_guild(self, client):
        client.guild.in_guild = False
        assert client.get(f"{URL}/options").status_code == 403

    def test_not_taken_by_poll_id_route(self, client):
        assert client.get(f"{URL}/options").status_code == 200


class TestCreate:
    def test_creates_and_sends(self, client):
        r = post(
            client,
            show_name=True,
            number_of_user_votes=2,
            only_roles=["600"],
            role_weights=[{"role_id": "602", "weight": 3}],
        )
        assert r.status_code == 200, r.text
        data = r.json()
        channel = client.guild.channels[500]
        assert len(channel.sent) == 1
        assert channel.sent[0]["embed"].footer.text == f"投票ID：{data['poll_id']}"
        assert data["message_url"] == f"https://discord.com/channels/{GUILD_ID}/500/9001"

        client.repo.session.expire_all()
        poll = client.repo.get_poll(data["poll_id"])
        assert (poll.creator_id, poll.channel_id, poll.message_id, poll.guild_id) == (OPERATOR, 500, 9001, GUILD_ID)
        assert (poll.show_name, poll.check_results_in_advance, poll.results_only_initiator) == (True, True, False)
        assert (poll.number_of_user_votes, poll.ban_alternate_account_voting, poll.can_change_vote) == (2, False, None)
        assert [o.option_name for o in client.repo.get_poll_options(poll.poll_id)] == ["拉麵", "咖哩"]
        roles = {r.role_id: (r.is_only_role, r.role_magnification) for r in client.repo.get_poll_role(poll.poll_id)}
        assert roles == {600: (True, 1), 602: (False, 3)}

    def test_trims_text_and_accepts_numeric_ids(self, client):
        r = post(client, channel_id=501, title="  標題  ", options=[" 甲 ", "乙"])
        assert r.status_code == 200
        client.repo.session.expire_all()
        poll = client.repo.get_poll(r.json()["poll_id"])
        assert poll.title == "標題"
        assert [o.option_name for o in client.repo.get_poll_options(poll.poll_id)] == ["甲", "乙"]

    @pytest.mark.parametrize(
        ("overrides", "path"),
        [
            ({"options": ["甲", "甲"]}, "options.1"),
            ({"options": [str(i) for i in range(21)]}, "options"),
            ({"title": "字" * 46}, "title"),
            ({"number_of_user_votes": 3}, "number_of_user_votes"),
            ({"role_weights": [{"role_id": "600", "weight": 11}]}, "role_weights.0.weight"),
            ({"role_weights": [{"role_id": "600", "weight": 0}]}, "role_weights.0.weight"),
            (
                {"role_weights": [{"role_id": "600", "weight": 2}, {"role_id": 600, "weight": 3}]},
                "role_weights",
            ),
            ({"only_roles": ["999"]}, "only_roles"),
            ({"only_roles": [str(GUILD_ID)]}, "only_roles"),
            ({"only_roles": ["601"]}, "only_roles"),
            ({"role_weights": [{"role_id": "999", "weight": 2}]}, "role_weights"),
            ({"only_roles": ["abc"]}, "only_roles"),
            ({"channel_id": "abc"}, "channel_id"),
            ({"channel_id": "999"}, "channel_id"),
            ({"channel_id": "504"}, "channel_id"),
        ],
    )
    def test_invalid_input_is_rejected(self, client, overrides, path):
        r = post(client, **overrides)
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_request"
        assert path in [f["path"] for f in r.json()["fields"]]
        assert poll_count(client) == client.before
        assert all(not c.sent for c in client.guild.channels.values())

    def test_multiple_errors_are_collected(self, client):
        r = post(client, title="", options=["甲", "甲"], channel_id="999")
        assert {f["path"] for f in r.json()["fields"]} == {"title", "options.1", "channel_id"}

    def test_bot_cannot_speak(self, client):
        r = post(client, channel_id="502")
        assert r.status_code == 400
        assert r.json() == {
            "error": "bot_missing_permission",
            "fields": [{"path": "channel_id", "reason": "星羽在這個頻道不能發言"}],
        }
        assert poll_count(client) == client.before

    def test_operator_cannot_speak(self, client):
        r = post(client, channel_id="503")
        assert r.status_code == 400
        assert r.json() == {
            "error": "invalid_request",
            "fields": [{"path": "channel_id", "reason": "你在這個頻道不能發言"}],
        }
        assert poll_count(client) == client.before
        assert not client.guild.channels[503].sent

    @pytest.mark.parametrize(
        ("cls", "status", "code", "text"),
        [
            (discord.Forbidden, 403, "no_permission", "星羽在這個頻道沒有發言權限"),
            (discord.NotFound, 404, "channel_missing", "頻道已不存在"),
            (discord.HTTPException, 500, "failed", "發送投票訊息時發生錯誤"),
        ],
    )
    def test_send_failure_creates_nothing(self, client, cls, status, code, text):
        client.guild.channels[500].send_error = cls(SimpleNamespace(status=status, reason=""), "")
        r = post(client)
        assert r.status_code == 400
        assert r.json() == {
            "error": "poll_send_failed",
            "message_failure": code,
            "message_failure_text": text,
        }
        assert poll_count(client) == client.before

    def test_needs_manage_messages(self, client):
        client.discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_CHANNELS)]
        assert post(client).status_code == 403
        assert poll_count(client) == client.before

    def test_operator_not_in_guild(self, client):
        client.guild.in_guild = False
        assert post(client).status_code == 403
        assert poll_count(client) == client.before

    def test_unauthenticated(self, client):
        client.cookies.clear()
        assert post(client).status_code == 401
