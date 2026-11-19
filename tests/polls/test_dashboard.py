"""伺服器管理後台 V-01：投票清單與詳細頁（假 Discord，真實 PostgreSQL）。"""

from __future__ import annotations

import pytest

from starlib.database import PollRole
from tests.helpers.dashboard_guilds import MANAGE_CHANNELS, g
from tests.helpers.dashboard_notifies import GUILD_ID
from tests.polls.dashboard_helpers import (
    CREATOR,
    LEFT,
    MEMBER,
    OTHER_GUILD,
    URL,
    VIEWER,
    add_poll,
    client,  # noqa: F401  (fixture)
    vote,
)

pytestmark = pytest.mark.usefixtures("dashboard_env")


class TestList:
    def test_empty(self, client):
        body = client.get(URL).json()
        assert body["polls"] == []
        assert body["has_next"] is False
        assert body["recent_days"] == 90

    def test_active_first_then_ended_newest_first(self, client):
        add_poll(client, title="舊結算", ended=True, ended_days_ago=5)
        add_poll(client, title="新結算", ended=True, ended_days_ago=1)
        add_poll(client, title="進行中")
        rows = client.get(URL).json()["polls"]
        assert [r["title"] for r in rows] == ["進行中", "新結算", "舊結算"]
        assert [r["status"] for r in rows] == ["active", "ended", "ended"]

    def test_voter_count_is_distinct_members_even_when_hidden(self, client):
        poll = add_poll(client, check=False)
        vote(client, poll, MEMBER, 1)
        vote(client, poll, MEMBER, 2)
        vote(client, poll, LEFT, 1)
        row = client.get(URL).json()["polls"][0]
        assert row["voter_count"] == 2
        assert "counts" not in row

    def test_row_fields(self, client):
        add_poll(client)
        row = client.get(URL).json()["polls"][0]
        assert row["creator_id"] == str(CREATOR)
        assert row["creator_name"] == "發起人"
        assert row["channel_id"] == "500"
        assert row["channel_name"] == "投票頻道"
        assert row["channel_state"] == "ok"
        assert row["missing_permissions"] == []
        assert row["message_url"] == f"https://discord.com/channels/{GUILD_ID}/500/900"
        assert row["deadline"] is None
        assert row["ended_at"] is None

    def test_other_guild_not_listed(self, client):
        add_poll(client, guild_id=OTHER_GUILD)
        assert client.get(URL).json()["polls"] == []

    def test_recent_filter_and_all(self, client):
        add_poll(client, title="很舊", ended=True, created_days_ago=100, ended_days_ago=99)
        add_poll(client, title="很舊但進行中", created_days_ago=100)
        titles = [r["title"] for r in client.get(URL).json()["polls"]]
        assert titles == ["很舊但進行中"]
        titles = [r["title"] for r in client.get(URL, params={"all": "true"}).json()["polls"]]
        assert titles == ["很舊但進行中", "很舊"]

    def test_pagination_and_active_only_on_first_page(self, client):
        add_poll(client, title="進行中")
        for i in range(21):
            add_poll(client, title=f"結算{i}", ended=True, ended_days_ago=i + 1)
        first = client.get(URL).json()
        assert len(first["polls"]) == 21  # 1 筆進行中 + 20 筆已結算
        assert first["has_next"] is True
        second = client.get(URL, params={"page": 2}).json()
        assert [r["title"] for r in second["polls"]] == ["結算20"]
        assert second["has_next"] is False

    def test_channel_unknown(self, client):
        add_poll(client, channel_id=None)
        row = client.get(URL).json()["polls"][0]
        assert row["channel_state"] == "unknown"
        assert row["channel_id"] is None
        assert row["channel_name"] is None
        assert row["message_url"] is None
        assert row["missing_permissions"] is None

    def test_channel_missing_has_no_permission_warning(self, client):
        add_poll(client, channel_id=999)
        row = client.get(URL).json()["polls"][0]
        assert row["channel_state"] == "missing"
        assert row["message_url"] is None
        assert row["missing_permissions"] is None

    def test_missing_permissions(self, client):
        add_poll(client, channel_id=501)
        assert client.get(URL).json()["polls"][0]["missing_permissions"] == ["讀取訊息歷史"]

    def test_ban_alt_excludes_alternate_account_from_voter_count(self, client):
        from starlib.database import UserAccount

        poll = add_poll(client, ban_alt=True)
        vote(client, poll, MEMBER, 1)
        vote(client, poll, LEFT, 1)
        client.repo.add(UserAccount(main_account=MEMBER, alternate_account=LEFT))
        assert client.get(URL).json()["polls"][0]["voter_count"] == 1


class TestAccess:
    def test_needs_manage_messages(self, client):
        client.discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_CHANNELS)]
        poll = add_poll(client)
        assert client.get(URL).status_code == 403
        assert client.get(f"{URL}/{poll.poll_id}").status_code == 403

    def test_other_guild_poll_is_404(self, client):
        poll = add_poll(client, guild_id=OTHER_GUILD)
        r = client.get(f"{URL}/{poll.poll_id}")
        assert r.status_code == 404
        assert r.json()["error"] == "poll_not_found"

    def test_missing_poll_is_404(self, client):
        assert client.get(f"{URL}/99999999").status_code == 404

    def test_unauthenticated(self, client):
        client.cookies.clear()
        assert client.get(URL).status_code == 401


class TestDetail:
    def test_everyone_sees_weighted_counts_and_names(self, client):
        poll = add_poll(client)
        vote(client, poll, MEMBER, 1, weight=3, minutes=1)
        vote(client, poll, LEFT, 1, minutes=2)
        vote(client, poll, CREATOR, 2, minutes=3)
        body = client.get(f"{URL}/{poll.poll_id}").json()
        assert body["results_visibility"] == "everyone"
        assert body["options"] == [{"option_id": 1, "name": "甲"}, {"option_id": 2, "name": "乙"}]
        assert body["counts"] == [
            {"option_id": 1, "name": "甲", "count": 4},
            {"option_id": 2, "name": "乙", "count": 1},
        ]
        assert body["voter_count"] == 3
        assert [(v["user_id"], v["name"], v["left"], v["option_id"], v["weight"]) for v in body["votes"]] == [
            (str(MEMBER), "成員", False, 1, 3),
            (str(LEFT), None, True, 1, 1),
            (str(CREATOR), "發起人", False, 2, 1),
        ]
        assert body["votes"][0]["voted_at"].endswith("+00:00") or "+" in body["votes"][0]["voted_at"]

    def test_anonymous_has_no_votes(self, client):
        poll = add_poll(client, show_name=False)
        vote(client, poll, MEMBER, 1)
        body = client.get(f"{URL}/{poll.poll_id}").json()
        assert body["counts"][0]["count"] == 1
        assert body["votes"] is None
        assert body["show_name"] is False

    def test_after_end_hidden_while_active_then_shown(self, client):
        poll = add_poll(client, check=False)
        vote(client, poll, MEMBER, 1)
        body = client.get(f"{URL}/{poll.poll_id}").json()
        assert body["results_visibility"] == "after_end"
        assert body["counts"] is None
        assert body["votes"] is None
        assert body["voter_count"] == 1
        ended = add_poll(client, check=False, ended=True)
        vote(client, ended, MEMBER, 1)
        body = client.get(f"{URL}/{ended.poll_id}").json()
        assert body["counts"][0]["count"] == 1
        assert body["votes"] is not None

    def test_check_off_overrides_only_initiator(self, client):
        poll = add_poll(client, check=False, only_initiator=True, creator_id=VIEWER)
        body = client.get(f"{URL}/{poll.poll_id}").json()
        assert body["results_visibility"] == "after_end"
        assert body["counts"] is None

    def test_creator_only_hides_from_other_admin(self, client):
        poll = add_poll(client, only_initiator=True)
        vote(client, poll, MEMBER, 1)
        body = client.get(f"{URL}/{poll.poll_id}").json()
        assert body["results_visibility"] == "creator_only"
        assert body["viewer"] == {"role": "member", "can_manage": False}
        assert body["counts"] is None
        assert body["votes"] is None

    def test_creator_only_visible_to_creator(self, client):
        poll = add_poll(client, only_initiator=True, creator_id=VIEWER)
        vote(client, poll, MEMBER, 1)
        body = client.get(f"{URL}/{poll.poll_id}").json()
        assert body["viewer"] == {"role": "creator", "can_manage": True}
        assert body["counts"][0]["count"] == 1

    def test_creator_only_visible_when_creator_left_guild(self, client):
        poll = add_poll(client, only_initiator=True, creator_id=LEFT)
        vote(client, poll, MEMBER, 1)
        body = client.get(f"{URL}/{poll.poll_id}").json()
        assert body["viewer"] == {"role": "creator", "can_manage": True}
        assert body["counts"] is not None

    def test_creator_only_visible_to_bot_owner(self, client):
        client.bot.owner_ids.add(VIEWER)
        poll = add_poll(client, only_initiator=True)
        body = client.get(f"{URL}/{poll.poll_id}").json()
        assert body["viewer"]["role"] == "creator"
        assert body["counts"] is not None

    def test_creator_only_shown_to_everyone_after_end(self, client):
        poll = add_poll(client, only_initiator=True, ended=True)
        vote(client, poll, MEMBER, 1)
        body = client.get(f"{URL}/{poll.poll_id}").json()
        assert body["viewer"]["role"] == "member"
        assert body["counts"][0]["count"] == 1

    def test_settings_roles_and_weights(self, client):
        poll = add_poll(client)
        client.repo.merge(PollRole(poll_id=poll.poll_id, role_id=600, is_only_role=True, role_magnification=1))
        client.repo.merge(PollRole(poll_id=poll.poll_id, role_id=601, is_only_role=False, role_magnification=5))
        body = client.get(f"{URL}/{poll.poll_id}").json()
        assert body["only_roles"] == [{"id": "600", "name": "成員身分組"}]
        assert body["role_weights"] == [{"id": "601", "name": None, "weight": 5}]
        assert body["number_of_user_votes"] == 1

    def test_message_failure_text(self, client):
        poll = add_poll(client, ended=True)
        poll.message_failure = "message_missing"
        client.repo.merge(poll)
        body = client.get(f"{URL}/{poll.poll_id}").json()
        assert body["message_failure"] == "message_missing"
        assert body["message_failure_text"]

    def test_no_failure(self, client):
        poll = add_poll(client)
        body = client.get(f"{URL}/{poll.poll_id}").json()
        assert body["message_failure"] is None
        assert body["message_failure_text"] is None

    def test_unknown_channel_has_no_link(self, client):
        poll = add_poll(client, channel_id=None)
        body = client.get(f"{URL}/{poll.poll_id}").json()
        assert body["channel_state"] == "unknown"
        assert body["message_url"] is None

    def test_ban_alt_excluded_from_counts_and_votes(self, client):
        from starlib.database import UserAccount

        poll = add_poll(client, ban_alt=True)
        vote(client, poll, MEMBER, 1)
        vote(client, poll, LEFT, 1)
        client.repo.add(UserAccount(main_account=MEMBER, alternate_account=LEFT))
        body = client.get(f"{URL}/{poll.poll_id}").json()
        assert body["counts"][0]["count"] == 1
        assert [v["user_id"] for v in body["votes"]] == [str(MEMBER)]
