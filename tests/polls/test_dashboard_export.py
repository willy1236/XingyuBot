"""V-05 投票匯出 CSV：可見範圍、內容、編碼、檔名與權限。"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from types import SimpleNamespace
from urllib.parse import unquote

import pytest

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


def export_url(poll) -> str:
    return f"{URL}/{poll.poll_id}/export.csv"


def rows(response) -> list[list[str]]:
    assert response.content.startswith(b"\xef\xbb\xbf")
    return list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))


class TestContent:
    def test_named_poll_has_counts_then_votes(self, client):
        poll = add_poll(client, title="午餐吃什麼")
        vote(client, poll, MEMBER, 1, weight=3, minutes=1)
        vote(client, poll, LEFT, 1, minutes=2)
        vote(client, poll, CREATOR, 2, minutes=3)
        r = client.get(export_url(poll))
        assert r.status_code == 200
        assert r.headers["content-type"] == "text/csv; charset=utf-8"
        data = rows(r)
        assert data[:3] == [["選項", "票數"], ["甲", "4"], ["乙", "1"]]
        assert data[3] == []
        assert data[4] == ["成員名稱", "成員 ID", "選項", "權重", "投票時間"]
        assert [d[:4] for d in data[5:]] == [
            ["成員", str(MEMBER), "甲", "3"],
            ["已離開的成員", str(LEFT), "甲", "1"],
            ["發起人", str(CREATOR), "乙", "1"],
        ]

    def test_times_are_taipei(self, client):
        poll = add_poll(client)
        vote(client, poll, MEMBER, 1)
        stored = client.repo.poll_vote_rows(poll.poll_id, True)[0][3]
        expected = stored.astimezone(UTC).timestamp() + 8 * 3600
        got = rows(client.get(export_url(poll)))[-1][4]
        assert datetime.strptime(got, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC).timestamp() == expected

    def test_anonymous_poll_only_has_counts(self, client):
        poll = add_poll(client, show_name=False)
        vote(client, poll, MEMBER, 1)
        assert rows(client.get(export_url(poll))) == [["選項", "票數"], ["甲", "1"], ["乙", "0"]]

    def test_formula_text_is_escaped_but_numbers_are_not(self, client):
        poll = add_poll(client, options=("=1+1", "-乙"))
        client.guild.members[MEMBER].display_name = "@成員"
        vote(client, poll, MEMBER, 1, weight=2)
        data = rows(client.get(export_url(poll)))
        assert data[1] == ["'=1+1", "2"]
        assert data[2] == ["'-乙", "0"]
        assert data[-1][:4] == ["'@成員", str(MEMBER), "'=1+1", "2"]


class TestVisibility:
    def test_hidden_until_end(self, client):
        poll = add_poll(client, check=False)
        r = client.get(export_url(poll))
        assert r.status_code == 403
        assert r.json() == {"error": "results_hidden"}

    def test_hidden_after_end_becomes_visible(self, client):
        poll = add_poll(client, check=False, ended=True)
        assert client.get(export_url(poll)).status_code == 200

    def test_creator_only_hides_from_other_admin(self, client):
        poll = add_poll(client, only_initiator=True)
        assert client.get(export_url(poll)).status_code == 403

    def test_creator_only_visible_to_creator(self, client):
        poll = add_poll(client, only_initiator=True, creator_id=VIEWER)
        client.guild.members[VIEWER] = SimpleNamespace(display_name="管理員")
        assert client.get(export_url(poll)).status_code == 200

    def test_creator_only_visible_when_creator_left(self, client):
        poll = add_poll(client, only_initiator=True, creator_id=LEFT)
        assert client.get(export_url(poll)).status_code == 200

    def test_creator_only_visible_to_bot_owner(self, client):
        poll = add_poll(client, only_initiator=True)
        client.bot.owner_ids.add(VIEWER)
        assert client.get(export_url(poll)).status_code == 200


class TestFilename:
    def test_includes_id_and_title(self, client):
        poll = add_poll(client, title='午餐/吃?什麼:"a"')
        disposition = client.get(export_url(poll)).headers["content-disposition"]
        assert disposition.startswith("attachment; ")
        encoded = disposition.split("filename*=UTF-8''")[1]
        assert unquote(encoded) == f"poll-{poll.poll_id}-午餐吃什麼a.csv"
        assert f'filename="poll-{poll.poll_id}-' in disposition

    def test_title_only_forbidden_chars(self, client):
        poll = add_poll(client, title="???")
        disposition = client.get(export_url(poll)).headers["content-disposition"]
        assert unquote(disposition.split("filename*=UTF-8''")[1]) == f"poll-{poll.poll_id}.csv"


class TestAccess:
    def test_needs_manage_messages(self, client):
        client.discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_CHANNELS)]
        poll = add_poll(client)
        assert client.get(export_url(poll)).status_code == 403

    def test_other_guild_poll_is_404(self, client):
        poll = add_poll(client, guild_id=OTHER_GUILD)
        r = client.get(f"{URL}/{poll.poll_id}/export.csv")
        assert r.status_code == 404
        assert r.json()["error"] == "poll_not_found"

    def test_unauthenticated(self, client):
        poll = add_poll(client)
        client.cookies.clear()
        assert client.get(export_url(poll)).status_code == 401
