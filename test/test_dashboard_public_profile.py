"""公開設定 /dashboard/personal/public 與公開頁 /dashboard/public/{username}（假 auth server，真實 PostgreSQL）。"""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_dashboard_auth import (  # noqa: F401  (fixture 與 helper)
    FRONTEND,
    USER_ID,
    dashboard_env,
    make_app,
    make_session,
)
from test_dashboard_domalyze_login import OTHER_ID, account
from test_identity import repo  # noqa: F401

from starlib import sclient
from starlib.database import Poll, PollOption, UserBet, UserPoll, VoiceTime
from starlib.database.postgresql.models import DiscordIdentity
from starlib.utils import nowtz
from starServer.dashboard import personal, public_profile
from starServer.dashboard.discord_users import DiscordProfile

OWN = int(USER_ID)
OTHER = int(OTHER_ID)
NOW = nowtz().replace(microsecond=0)
ACCOUNT_ID = uuid4()
HEADERS = {"Origin": FRONTEND}
#: 兩個 Discord 依 ID 由小到大，對應「帳號一」「帳號二」
FIRST, SECOND = sorted((OWN, OTHER))


@pytest.fixture
def client(repo, dashboard_env, monkeypatch) -> TestClient:  # noqa: F811
    monkeypatch.setattr(public_profile, "sqldb", repo)
    monkeypatch.setattr(personal, "sqldb", repo)
    monkeypatch.setattr(sclient, "bot", None)
    dashboard_env.directory.accounts[OWN] = account(ACCOUNT_ID, (OTHER, OWN))
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
    make_session(repo)
    c.cookies.set("dashboard_session", "sid")
    return c


@pytest.fixture
def visitor(client) -> TestClient:
    """沒有 cookie 的訪客"""
    return TestClient(client.app, base_url="https://testserver", follow_redirects=False)


def set_profile(repo, enabled=True, sections=()):  # noqa: F811
    repo.save_public_profile(ACCOUNT_ID, enabled, list(sections))


def put_settings(client, enabled=True, sections=()):
    return client.put("/dashboard/personal/public", json={"enabled": enabled, "sections": list(sections)}, headers=HEADERS)


def get_public(visitor, name="willy"):
    return visitor.get(f"/dashboard/public/{name}")


class TestSettings:
    def test_default_off(self, client):
        assert client.get("/dashboard/personal/public").json() == {"available": True, "enabled": False, "sections": [], "username": "willy"}

    def test_put_saves_in_canonical_order_and_dedupes(self, client, repo):  # noqa: F811
        res = put_settings(client, True, ["voice", "points", "voice"])
        assert res.json() == {"available": True, "enabled": True, "sections": ["points", "voice"], "username": "willy"}
        assert repo.get_public_profile(ACCOUNT_ID).sections == ["points", "voice"]
        assert client.get("/dashboard/personal/public").json()["sections"] == ["points", "voice"]

    @pytest.mark.parametrize("section", ["warnings", "drive", "netbird", "bogus"])
    def test_unknown_or_forbidden_section(self, client, section):
        res = put_settings(client, True, [section])
        assert (res.status_code, res.json()) == (400, {"error": "invalid_request"})

    def test_without_account_locked(self, repo, dashboard_env, monkeypatch):  # noqa: F811
        monkeypatch.setattr(public_profile, "sqldb", repo)
        monkeypatch.setattr(personal, "sqldb", repo)

        async def no_identity(discord_id, *, create=True):
            return None

        monkeypatch.setattr(personal, "resolve_identity", no_identity)
        c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
        make_session(repo)
        c.cookies.set("dashboard_session", "sid")
        assert c.get("/dashboard/personal/public").json() == {"available": False}
        res = put_settings(c, True, [])
        assert (res.status_code, res.json()) == (403, {"error": "domalyze_required"})

    def test_put_requires_session(self, client):
        client.cookies.clear()
        assert put_settings(client, True, []).status_code == 401


class TestPublicPage:
    def test_not_enabled_is_404(self, client, visitor):
        res = get_public(visitor)
        assert (res.status_code, res.json()) == (404, {"error": "not_found"})

    def test_disabled_with_sections_is_404(self, client, visitor, repo):  # noqa: F811
        set_profile(repo, enabled=False, sections=["points"])
        assert get_public(visitor).status_code == 404

    def test_unknown_username_same_as_disabled(self, client, visitor):
        assert get_public(visitor, "nobody").json() == {"error": "not_found"}

    def test_enabled_without_sections(self, client, visitor, repo):  # noqa: F811
        set_profile(repo)
        res = get_public(visitor)
        assert res.status_code == 200
        assert res.json() == {"username": "willy", "sections": [], "discords": [], "playlists": None}

    def test_only_points_no_ids_or_other_fields(self, client, visitor, repo):  # noqa: F811
        set_profile(repo, sections=["points"])
        body = get_public(visitor).json()
        assert body["sections"] == ["points"]
        assert body["playlists"] is None
        assert [sorted(d) for d in body["discords"]] == [["label", "points"], ["label", "points"]]
        text = str(body)
        assert str(OWN) not in text and str(OTHER) not in text and str(ACCOUNT_ID) not in text

    def test_labels_ordered_by_discord_id(self, client, visitor, repo):  # noqa: F811
        minutes = {OWN: 10, OTHER: 20}
        for discord_id, m in minutes.items():
            repo.session.add(VoiceTime(discord_id=discord_id, guild_id=1, total_minute=timedelta(minutes=m)))
        repo.session.commit()
        set_profile(repo, sections=["voice"])
        discords = get_public(visitor).json()["discords"]
        assert [(d["label"], d["voice_minutes"]) for d in discords] == [("帳號一", minutes[FIRST]), ("帳號二", minutes[SECOND])]

    def test_voice_total_across_guilds_without_guild_info(self, client, visitor, repo):  # noqa: F811
        repo.session.add_all(
            [
                VoiceTime(discord_id=OWN, guild_id=1, total_minute=timedelta(hours=1, seconds=59)),
                VoiceTime(discord_id=OWN, guild_id=2, total_minute=timedelta(minutes=5)),
            ]
        )
        repo.session.commit()
        set_profile(repo, sections=["voice"])
        res = get_public(visitor)
        assert {d["voice_minutes"] for d in res.json()["discords"]} == {65, 0}
        assert "guild" not in res.text

    def test_participation_counts_only(self, client, visitor, repo):  # noqa: F811
        poll = Poll(guild_id=1, title="秘密標題", created_user=OWN, created_at=NOW, is_on=True)
        repo.session.add(poll)
        repo.session.flush()
        repo.session.add_all(
            [
                PollOption(poll_id=poll.poll_id, option_id=1, option_name="秘密選項一"),
                PollOption(poll_id=poll.poll_id, option_id=2, option_name="秘密選項二"),
                UserPoll(poll_id=poll.poll_id, discord_id=OWN, vote_option=1, vote_at=NOW),
                UserPoll(poll_id=poll.poll_id, discord_id=OWN, vote_option=2, vote_at=NOW),
                UserBet(discord_id=OWN, bet_id=1, bet_option=1, bet_amount=777, bet_at=NOW),
                UserBet(discord_id=OWN, bet_id=2, bet_option=2, bet_amount=888, bet_at=NOW),
            ]
        )
        repo.session.commit()
        set_profile(repo, sections=["participation"])
        res = get_public(visitor)
        mine = {"polls": 1, "bets": 2, "giveaways": 0}
        empty = {"polls": 0, "bets": 0, "giveaways": 0}
        expected = {FIRST: mine if FIRST == OWN else empty, SECOND: mine if SECOND == OWN else empty}
        assert [d["participation"] for d in res.json()["discords"]] == [expected[FIRST], expected[SECOND]]
        for secret in ("秘密", "777", "888"):
            assert secret not in res.text

    def test_playlists(self, client, visitor, repo):  # noqa: F811
        pl = repo.create_music_playlist(ACCOUNT_ID, "我的歌單")
        repo.add_music_playlist_songs(pl.id, [("https://example.com/a", "歌 A", None), ("https://example.com/b", "歌 B", None)])
        repo.create_music_playlist(uuid4(), "別人的")
        set_profile(repo, sections=["playlists"])
        body = get_public(visitor).json()
        assert body["discords"] == []
        assert body["playlists"] == [
            {
                "name": "我的歌單",
                "songs": [{"title": "歌 A", "url": "https://example.com/a"}, {"title": "歌 B", "url": "https://example.com/b"}],
            }
        ]

    def test_discord_names_hidden_unless_checked(self, client, visitor, repo):  # noqa: F811
        set_profile(repo, sections=["points"])
        res = get_public(visitor)
        assert all(set(d) == {"label", "points"} for d in res.json()["discords"])
        assert "avatar" not in res.text and str(OWN) not in res.text and str(OTHER) not in res.text

    def test_discord_names_shown_when_checked(self, client, visitor, repo, monkeypatch):  # noqa: F811
        async def fake_fetch(discord_id):
            return DiscordProfile("名字", None) if discord_id == FIRST else None

        monkeypatch.setattr(public_profile, "fetch_discord_user", fake_fetch)
        set_profile(repo, sections=["discord_names"])
        discords = get_public(visitor).json()["discords"]
        assert [(d["label"], d["name"]) for d in discords] == [("帳號一", "名字"), ("帳號二", None)]
        assert discords[0]["avatar_url"].startswith("https://cdn.discordapp.com/")
        assert discords[1]["avatar_url"] is None

    def test_pet_has_no_food(self, client, visitor, repo, monkeypatch):  # noqa: F811
        monkeypatch.setattr(
            public_profile,
            "_assets",
            lambda ids: [({"stardust": 1, "point": 2, "rcoin": 3}, {"name": "小白", "species": "貓", "food": 99}) for _ in ids],
        )
        set_profile(repo, sections=["pets"])
        discords = get_public(visitor).json()["discords"]
        assert discords[0] == {"label": "帳號一", "pet": {"name": "小白", "species": "貓"}}

    def test_setting_takes_effect_on_next_request_without_cache(self, client, visitor):
        assert get_public(visitor).status_code == 404
        put_settings(client, True, ["points"])
        assert get_public(visitor).json()["sections"] == ["points"]
        put_settings(client, True, [])
        assert get_public(visitor).json()["sections"] == []
        put_settings(client, False, [])
        assert get_public(visitor).status_code == 404

    def test_suspended_is_404(self, client, visitor, repo, dashboard_env):  # noqa: F811
        set_profile(repo, sections=["points"])
        dashboard_env.directory.accounts[OWN] = account(ACCOUNT_ID, (OWN, OTHER), suspended=True)
        assert get_public(visitor).json() == {"error": "not_found"}

    def test_username_change(self, client, visitor, repo, dashboard_env):  # noqa: F811
        set_profile(repo, sections=["points"])
        dashboard_env.directory.accounts[OWN] = account(ACCOUNT_ID, (OWN, OTHER), username="renamed")
        assert get_public(visitor, "willy").status_code == 404
        assert get_public(visitor, "renamed").json()["username"] == "renamed"

    def test_directory_unavailable_is_503(self, client, visitor, repo, dashboard_env):  # noqa: F811
        set_profile(repo)
        dashboard_env.directory.unavailable = True
        res = get_public(visitor)
        assert (res.status_code, res.json()) == (503, {"error": "directory_unavailable"})

    def test_no_session_needed_and_no_cookie_set(self, client, visitor, repo):  # noqa: F811
        set_profile(repo)
        res = get_public(visitor)
        assert res.status_code == 200
        assert "set-cookie" not in res.headers

    def test_overlong_username_is_404(self, visitor):
        assert get_public(visitor, "a" * 200).status_code == 404


class TestMerge:
    def test_merge_deletes_source_profile_and_keeps_survivor(self, repo):  # noqa: F811
        old, new = uuid4(), uuid4()
        repo.save_public_profile(old, True, ["points"])
        repo.save_public_profile(new, False, [])
        repo.merge_user_data(old, new)
        assert repo.get_public_profile(old) is None
        survivor = repo.get_public_profile(new)
        assert (survivor.enabled, survivor.sections) == (False, [])

    def test_merge_survivor_without_profile_stays_off(self, repo):  # noqa: F811
        old, new = uuid4(), uuid4()
        repo.save_public_profile(old, True, ["points", "voice"])
        repo.merge_user_data(old, new)
        assert repo.get_public_profile(old) is None
        assert repo.get_public_profile(new) is None

    def test_save_discord_identity_merge_path(self, repo):  # noqa: F811
        old, new = uuid4(), uuid4()
        repo.save_public_profile(old, True, ["points"])
        identity = DiscordIdentity(discord_id=424242, user_id=new, is_formal=True, username="u", roles=[], suspended=False, checked_at=nowtz())
        repo.save_discord_identity(identity, merge_from=old)
        assert repo.get_public_profile(old) is None
