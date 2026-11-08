"""伺服器管理後台 T-07：社群推播的帳號解析、設定服務、條件式寫入與端點。"""

from __future__ import annotations

import subprocess
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select
from test_dashboard_auth import FRONTEND, dashboard_env, make_app, make_session  # noqa: F401  (fixture 與 helper)
from test_dashboard_guilds import MANAGE_CHANNELS, g, seed_token
from test_dashboard_guilds import discord as discord_env  # noqa: F401  (fixture)
from test_dashboard_notifies import GUILD_ID, LOCKED_ROLE, OK_CHANNEL, OK_ROLE, fake_bot, fake_guild
from test_identity import repo  # noqa: F401

from starlib import notify_settings, sclient
from starlib.database import Community, CommunityCache, NotifyCommunity, PushRecord
from starlib.database import NotifyCommunityType as N
from starlib.database import PlatformType as P
from starlib.exceptions import APINetworkError, NotifyCommunityExistsError
from starlib.notify_settings import AccountInfo, LookupFailure, ParsedInput, parse_input
from starlib.utils import nowtz
from starServer.dashboard import community_notifies

TW = AccountInfo(P.Twitch, "100", "Foo", "foo")
YT = AccountInfo(P.Google, "UCaaaaaaaaaaaaaaaaaaaaaa", "頻道", "@chan")
OTHER_GUILD = GUILD_ID + 1


def fail_reason(platform, text) -> str:
    with pytest.raises(LookupFailure) as e:
        parse_input(platform, text)
    return e.value.reason


class TestParseInput:
    @pytest.mark.parametrize(
        "text",
        ["Foo", "foo", "twitch.tv/foo", "https://twitch.tv/Foo", "https://www.twitch.tv/foo/videos?x=1", "HTTP://M.TWITCH.TV/FOO", "@foo"],
    )
    def test_twitch(self, text):
        assert parse_input(P.Twitch, text) == ParsedInput("name", "foo")

    @pytest.mark.parametrize(
        "text",
        ["chan_1", "@chan_1", "youtube.com/@chan_1", "https://www.youtube.com/@chan_1/videos?x=1", "https://m.youtube.com/@Chan_1"],
    )
    def test_youtube_handle(self, text):
        assert parse_input(P.Google, text).kind == "name"
        assert parse_input(P.Google, text).value.lower() == "@chan_1"

    @pytest.mark.parametrize("text", ["UCaaaaaaaaaaaaaaaaaaaaaa", "youtube.com/channel/UCaaaaaaaaaaaaaaaaaaaaaa", "https://www.youtube.com/channel/UCaaaaaaaaaaaaaaaaaaaaaa?x=1"])
    def test_youtube_channel_id(self, text):
        assert parse_input(P.Google, text) == ParsedInput("id", "UCaaaaaaaaaaaaaaaaaaaaaa")

    @pytest.mark.parametrize("text", ["foo", "@foo", "x.com/foo", "https://twitter.com/Foo/status/1", "https://www.x.com/foo?s=20", "https://mobile.twitter.com/foo"])
    def test_twitter(self, text):
        assert parse_input(P.Twitter, text).value.lower() == "foo"

    def test_twitter_numeric_is_id(self):
        assert parse_input(P.Twitter, "12345") == ParsedInput("id", "12345")

    @pytest.mark.parametrize(
        ("platform", "text"),
        [
            (P.Twitch, ""),
            (P.Twitch, "bad name"),
            (P.Twitch, "a" * 26),
            (P.Twitch, "https://youtube.com/@foo"),  # 別的平台的網址
            (P.Twitch, "https://twitch.tv/"),
            (P.Google, "https://www.youtube.com/watch?v=abc"),
            (P.Google, "https://www.youtube.com/c/oldname"),
            (P.Google, "ab"),
            (P.Twitter, "https://x.com/home"),
            (P.Twitter, "a" * 16),
        ],
    )
    def test_unsupported(self, platform, text):
        assert fail_reason(platform, text) == "unsupported_format"


class FakeApis:
    def __init__(self, monkeypatch):
        self.calls: list = []
        self.tw_user = SimpleNamespace(id=100, display_name="Foo", login="foo")
        self.tw_error: Exception | None = None
        self.yt_channel = SimpleNamespace(id=YT.id, snippet=SimpleNamespace(title="頻道", customUrl="@chan"))
        self.yt_error: Exception | None = None
        self.twitter_user = SimpleNamespace(id=7, fullName="Tw Name", userName="twname")
        self.twitter_error: Exception | None = None
        self.add_push_ok = True
        self.push_verified = True
        self.push_error: Exception | None = None
        times = (nowtz().replace(microsecond=0), nowtz().replace(microsecond=0) + timedelta(days=5))
        monkeypatch.setattr(
            notify_settings,
            "tw_api",
            SimpleNamespace(get_user=lambda v: self._tw("login", v), get_user_by_id=lambda v: self._tw("id", v)),
        )
        monkeypatch.setattr(notify_settings, "google_api", SimpleNamespace(get_channel=self._yt))
        monkeypatch.setattr(notify_settings, "cli_api", SimpleNamespace(get_user_details=self._twitter))
        monkeypatch.setattr(
            notify_settings,
            "yt_push",
            SimpleNamespace(
                add_push=self._add_push,
                get_push=lambda *a: self._get_push(times),
            ),
        )
        monkeypatch.setattr(notify_settings, "PUSH_VERIFY_WAIT", 0)
        self.times = times

    def _tw(self, kind, value):
        self.calls.append(("twitch", kind, value))
        if self.tw_error:
            raise self.tw_error
        return self.tw_user

    def _yt(self, channel_id=None, handle=None):
        self.calls.append(("youtube", channel_id, handle))
        if self.yt_error:
            raise self.yt_error
        return self.yt_channel

    def _twitter(self, value, strict=False):
        self.calls.append(("twitter", value, strict))
        if self.twitter_error:
            raise self.twitter_error
        return self.twitter_user

    def _add_push(self, *a):
        self.calls.append(("add_push", a[0]))
        return self.add_push_ok

    def _get_push(self, times):
        if self.push_error:
            raise self.push_error
        return SimpleNamespace(has_verify=self.push_verified, last_successful_verification=times[0], expiration_time=times[1])


def http_error(status: int | None) -> APINetworkError:
    original = SimpleNamespace(response=SimpleNamespace(status_code=status)) if status else None
    return APINetworkError(original=original)  # pyright: ignore[reportArgumentType]


@pytest.fixture
def apis(monkeypatch, repo, dashboard_env):  # noqa: F811
    monkeypatch.setattr(notify_settings, "sqldb", repo)
    monkeypatch.setattr(community_notifies, "sqldb", repo)
    monkeypatch.setattr(community_notifies, "_resolved", {})
    return FakeApis(monkeypatch)


class TestResolveAccount:
    def test_twitch(self, apis):
        assert notify_settings.resolve_account(P.Twitch, "https://www.twitch.tv/Foo") == TW
        assert apis.calls == [("twitch", "login", "foo")]

    def test_youtube_with_and_without_handle(self, apis):
        assert notify_settings.resolve_account(P.Google, "@chan") == YT
        apis.yt_channel.snippet.customUrl = None
        assert notify_settings.resolve_account(P.Google, "@chan").username == YT.id  # 沒有 handle 存頻道 ID

    def test_twitter_strict(self, apis):
        assert notify_settings.resolve_account(P.Twitter, "@twname").username == "twname"
        assert apis.calls == [("twitter", "twname", True)]

    @pytest.mark.parametrize("platform", [P.Twitch, P.Google, P.Twitter])
    def test_not_found(self, apis, platform):
        apis.tw_user = apis.yt_channel = apis.twitter_user = None
        with pytest.raises(LookupFailure) as e:
            notify_settings.resolve_account(platform, "abc_def")
        assert e.value.reason == "not_found"

    def test_format_rejected_without_calling_platform(self, apis):
        with pytest.raises(LookupFailure):
            notify_settings.resolve_account(P.Twitch, "bad name")
        assert apis.calls == []

    @pytest.mark.parametrize(
        ("platform", "attr", "error", "reason"),
        [
            (P.Twitch, "tw_error", http_error(400), "unsupported_format"),
            (P.Twitch, "tw_error", http_error(500), "platform_unavailable"),
            (P.Twitch, "tw_error", http_error(429), "platform_unavailable"),
            (P.Twitch, "tw_error", http_error(None), "platform_unavailable"),
            (P.Google, "yt_error", http_error(403), "platform_unavailable"),
            (P.Twitter, "twitter_error", subprocess.CalledProcessError(1, "rettiwt"), "platform_unavailable"),
            (P.Twitter, "twitter_error", subprocess.TimeoutExpired("rettiwt", 30), "platform_unavailable"),
            (P.Twitter, "twitter_error", FileNotFoundError("rettiwt"), "platform_unavailable"),
            (P.Twitter, "twitter_error", ValueError, "platform_unavailable"),
        ],
    )
    def test_platform_errors(self, apis, platform, attr, error, reason):
        if error is ValueError:  # JSONDecodeError 是 ValueError 的子類，這裡直接用它
            import json

            error = json.JSONDecodeError("x", "", 0)
        setattr(apis, attr, error)
        with pytest.raises(LookupFailure) as e:
            notify_settings.resolve_account(platform, "abc_def")
        assert e.value.reason == reason


def notify_row(repo, notify_type, guild_id=GUILD_ID, community_id="100"):
    return repo.get_notify_community_fresh(notify_type, community_id, guild_id)


def cache_types(repo, community_id="100") -> set:
    repo.session.expire_all()
    return {c.notify_type for c in repo.session.exec(select(CommunityCache).where(CommunityCache.community_id == community_id)).all()}


class TestRepository:
    def test_insert_many_writes_all_three_tables(self, repo):
        repo.insert_notify_communities(TW.to_community(), [N.TwitchLive, N.TwitchClip], GUILD_ID, 5, 6, "hi", nowtz())
        assert (notify_row(repo, N.TwitchLive).channel_id, notify_row(repo, N.TwitchClip).role_id) == (5, 6)
        community = repo.session.get(Community, ("100", P.Twitch))
        assert (community.username, community.display_name) == ("foo", "Foo")
        assert cache_types(repo) == {N.TwitchLive, N.TwitchClip}
        assert len(repo.get_notify_community_list(N.TwitchLive, GUILD_ID)) == 1  # 指令 list 的 inner join 查得到

    def test_any_existing_blocks_whole_batch(self, repo):
        repo.insert_notify_communities(TW.to_community(), [N.TwitchLive], GUILD_ID, 5, None, None, nowtz())
        with pytest.raises(NotifyCommunityExistsError) as e:
            repo.insert_notify_communities(TW.to_community(), [N.TwitchLive, N.TwitchVideo, N.TwitchClip], GUILD_ID, 9, None, None, nowtz())
        assert e.value.notify_types == [N.TwitchLive]
        assert notify_row(repo, N.TwitchVideo) is None and notify_row(repo, N.TwitchClip) is None
        assert notify_row(repo, N.TwitchLive).channel_id == 5

    def test_other_guild_subscribed_is_not_a_conflict(self, repo):
        repo.insert_notify_communities(TW.to_community(), [N.TwitchLive], OTHER_GUILD, 5, None, None, nowtz())
        repo.insert_notify_communities(TW.to_community(), [N.TwitchLive], GUILD_ID, 6, None, None, nowtz())
        assert notify_row(repo, N.TwitchLive).channel_id == 6

    def test_update_if(self, repo):
        repo.insert_notify_communities(TW.to_community(), [N.TwitchLive], GUILD_ID, 5, None, None, nowtz())
        orig = {"channel_id": 5, "role_id": None, "message": None}
        assert repo.update_notify_community_if(N.TwitchLive, "100", GUILD_ID, orig, {"channel_id": 8, "role_id": 3, "message": "m"}) == 1
        assert repo.update_notify_community_if(N.TwitchLive, "100", GUILD_ID, orig, {"channel_id": 9}) == 0
        row = notify_row(repo, N.TwitchLive)
        assert (row.channel_id, row.role_id, row.message) == (8, 3, "m")

    def test_delete_if_cleans_up(self, repo):
        repo.insert_notify_communities(TW.to_community(), [N.TwitchLive], GUILD_ID, 5, None, None, nowtz())
        assert repo.delete_notify_community_if(N.TwitchLive, "100", GUILD_ID, {"channel_id": 6, "role_id": None, "message": None}) == 0
        assert repo.delete_notify_community_if(N.TwitchLive, "100", GUILD_ID, {"channel_id": 5, "role_id": None, "message": None}) == 1
        assert repo.session.get(Community, ("100", P.Twitch)) is None
        assert cache_types(repo) == set()


class TestCleanup:
    def test_each_type_cache_follows_its_own_subscribers(self, repo):
        repo.insert_notify_communities(TW.to_community(), [N.TwitchLive, N.TwitchClip], GUILD_ID, 5, None, None, nowtz())
        repo.remove_notify_community(N.TwitchLive, "100", GUILD_ID)
        # 開台沒人訂閱了，輪詢紀錄要清掉；剪輯仍有人訂閱
        assert cache_types(repo) == {N.TwitchClip}
        assert repo.session.get(Community, ("100", P.Twitch)) is not None
        repo.remove_notify_community(N.TwitchClip, "100", GUILD_ID)
        assert cache_types(repo) == set()
        assert repo.session.get(Community, ("100", P.Twitch)) is None

    def test_other_guild_keeps_cache(self, repo):
        repo.insert_notify_communities(TW.to_community(), [N.TwitchLive], GUILD_ID, 5, None, None, nowtz())
        repo.insert_notify_communities(TW.to_community(), [N.TwitchLive], OTHER_GUILD, 5, None, None, nowtz())
        repo.remove_notify_community(N.TwitchLive, "100", GUILD_ID)
        assert cache_types(repo) == {N.TwitchLive}
        assert repo.session.get(Community, ("100", P.Twitch)) is not None

    def test_youtube_push_record_removed_with_last_notify(self, repo):
        repo.insert_notify_communities(YT.to_community(), [N.Youtube], GUILD_ID, 5, None, None, nowtz())
        repo.session.merge(PushRecord(channel_id=YT.id))
        repo.session.commit()
        repo.remove_notify_community(N.Youtube, YT.id, GUILD_ID)
        assert repo.session.get(PushRecord, YT.id) is None
        assert repo.session.get(Community, (YT.id, P.Google)) is None


class TestSettingsService:
    def test_set_notify_inserts_then_updates(self, apis, repo):
        notify_settings.set_notify(TW, N.TwitchLive, GUILD_ID, 5, None, "a")
        notify_settings.set_notify(TW, N.TwitchLive, GUILD_ID, 6, 7, "b")
        row = notify_row(repo, N.TwitchLive)
        assert (row.channel_id, row.role_id, row.message) == (6, 7, "b")

    def test_ensure_push_flows(self, apis, repo):
        # 沒有紀錄：訂閱並存下驗證時間，保留原有欄位
        repo.session.merge(PushRecord(channel_id=YT.id, secret="keep"))
        repo.session.commit()
        monkey_config = SimpleNamespace(callback_uri="https://cb", hub_secret="s")
        repo.get_websub_config = lambda *a: monkey_config
        assert notify_settings.ensure_youtube_push(YT.id) == "ok"
        record = repo.get_push_record(YT.id)
        assert record.expire_at == apis.times[1] and record.secret == "keep"
        # 仍有效：不再訂閱
        apis.calls.clear()
        assert notify_settings.ensure_youtube_push(YT.id) == "ok"
        assert apis.calls == []

    @pytest.mark.parametrize(
        ("setup", "expected"),
        [
            (lambda a: setattr(a, "add_push_ok", False), "failed"),
            (lambda a: setattr(a, "push_error", http_error(404)), "failed"),
            (lambda a: setattr(a, "push_error", AttributeError("None.json")), "failed"),
            (lambda a: setattr(a, "push_verified", False), "pending"),
        ],
    )
    def test_push_not_saved_unless_verified(self, apis, repo, setup, expected):
        repo.get_websub_config = lambda *a: SimpleNamespace(callback_uri="https://cb", hub_secret="s")
        setup(apis)
        assert notify_settings.ensure_youtube_push(YT.id) == expected
        assert repo.get_push_record(YT.id).is_expired


class TestEndpoints:
    @pytest.fixture
    def client(self, discord_env, repo, dashboard_env, apis, monkeypatch) -> TestClient:  # noqa: F811
        seed_token(repo, dashboard_env.credential_id)
        make_session(repo)
        discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_CHANNELS)]
        monkeypatch.setattr(sclient, "bot", fake_bot(fake_guild()))
        repo.get_websub_config = lambda *a: SimpleNamespace(callback_uri="https://cb", hub_secret="s")
        c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
        c.cookies.set("dashboard_session", "sid")
        c.repo = repo  # pyright: ignore[reportAttributeAccessIssue]
        c.apis = apis  # pyright: ignore[reportAttributeAccessIssue]
        return c

    base = f"/dashboard/guilds/{GUILD_ID}/community-notifies"
    headers = {"Origin": FRONTEND}

    def resolve(self, client, platform="twitch", text="foo"):
        return client.post(f"{self.base}/resolve", json={"platform": platform, "input": text}, headers=self.headers)

    def create(self, client, types, values=None, platform="twitch", account_id="100"):
        values = values or {"channel_id": str(OK_CHANNEL)}
        body = {"platform": platform, "account_id": account_id, "notify_types": types, "values": values}
        return client.post(self.base, json=body, headers=self.headers)

    def put(self, client, key, account_id, values, original):
        return client.put(f"{self.base}/{key}/{account_id}", json={"values": values, "original": original}, headers=self.headers)

    def delete(self, client, key, account_id, original):
        return client.request("DELETE", f"{self.base}/{key}/{account_id}", json={"original": original}, headers=self.headers)

    def test_resolve(self, client):
        res = self.resolve(client, text="https://twitch.tv/Foo")
        assert res.json() == {"platform": "twitch", "account_id": "100", "display_name": "Foo", "username": "foo"}

    @pytest.mark.parametrize(
        ("setup", "reason"),
        [
            (lambda a: setattr(a, "tw_user", None), "not_found"),
            (lambda a: setattr(a, "tw_error", http_error(503)), "platform_unavailable"),
        ],
    )
    def test_resolve_failed(self, client, setup, reason):
        setup(client.apis)
        res = self.resolve(client)
        assert (res.status_code, res.json()) == (400, {"error": "resolve_failed", "reason": reason})

    def test_resolve_unsupported_format(self, client):
        assert self.resolve(client, text="bad name").json() == {"error": "resolve_failed", "reason": "unsupported_format"}

    def test_create_multiple_twitch_types_separately_editable(self, client):
        self.resolve(client)
        res = self.create(client, ["community:1", "community:4"], {"channel_id": str(OK_CHANNEL), "role_id": str(OK_ROLE), "message": "hi"})
        assert res.status_code == 200
        assert notify_row(client.repo, N.TwitchLive).message == "hi"
        # 兩筆可以設在不同頻道；刪掉其中一筆，另一筆不受影響
        orig = {"channel_id": str(OK_CHANNEL), "role_id": str(OK_ROLE), "message": "hi"}
        assert self.put(client, "community:4", "100", {"channel_id": "15", "role_id": None}, orig).status_code == 200
        assert self.delete(client, "community:1", "100", orig).status_code == 200
        assert notify_row(client.repo, N.TwitchClip).channel_id == 15
        assert notify_row(client.repo, N.TwitchLive) is None
        assert cache_types(client.repo) == {N.TwitchClip}

    def test_create_uses_resolved_cache_not_client_names(self, client):
        self.resolve(client)
        client.apis.calls.clear()
        self.create(client, ["community:1"])
        assert client.apis.calls == []  # 快取命中，不再查平台
        assert client.repo.session.get(Community, ("100", P.Twitch)).username == "foo"

    def test_create_refetches_by_id_when_cache_expired(self, client):
        assert self.create(client, ["community:1"]).status_code == 200
        assert client.apis.calls == [("twitch", "id", "100")]

    def test_create_existing_blocks_batch_and_lists_existing(self, client):
        self.create(client, ["community:1"])
        res = self.create(client, ["community:1", "community:3", "community:4"], {"channel_id": "15"})
        assert res.status_code == 409
        assert res.json() == {
            "error": "already_exists",
            "existing": ["community:1"],
            "current": {"community:1": {"channel_id": str(OK_CHANNEL), "role_id": None, "message": None}},
        }
        assert notify_row(client.repo, N.TwitchVideo) is None

    def test_create_validates_fields(self, client):
        res = self.create(client, ["community:1"], {"channel_id": "999"})
        assert res.json()["error"] == "invalid_field" and res.json()["field"] == "channel_id"
        res = self.create(client, ["community:1"], {"channel_id": str(OK_CHANNEL), "role_id": str(LOCKED_ROLE)})
        assert res.json()["field"] == "role_id"

    @pytest.mark.parametrize(
        ("types", "platform"),
        [([], "twitch"), (["community:2"], "twitch"), (["channel:1"], "twitch"), (["community:1"], "bogus"), (["community:1"], "youtube")],
    )
    def test_create_bad_request(self, client, types, platform):
        assert self.create(client, types, platform=platform).json() == {"error": "invalid_request"}

    def test_twitter_has_no_message(self, client):
        res = self.create(client, ["community:5"], {"channel_id": str(OK_CHANNEL), "message": "ignored"}, platform="twitter", account_id="7")
        assert res.status_code == 200
        assert notify_row(client.repo, N.TwitterTweet, community_id="7").message is None

    def test_update_only_changes_allowed_fields(self, client):
        self.create(client, ["community:1"])
        orig = {"channel_id": str(OK_CHANNEL), "role_id": None, "message": None}
        assert self.put(client, "community:1", "100", {"channel_id": "15", "role_id": str(OK_ROLE), "message": "x"}, orig).status_code == 200
        row = notify_row(client.repo, N.TwitchLive)
        assert (row.channel_id, row.role_id, row.message) == (15, OK_ROLE, "x")

    def test_update_and_delete_conflict(self, client):
        self.create(client, ["community:1"])
        client.repo.update_notify_community_if(N.TwitchLive, "100", GUILD_ID, {"channel_id": OK_CHANNEL}, {"channel_id": 15})
        orig = {"channel_id": str(OK_CHANNEL), "role_id": None, "message": None}
        res = self.put(client, "community:1", "100", {"channel_id": str(OK_CHANNEL)}, orig)
        assert res.status_code == 409
        assert res.json() == {"error": "conflict", "deleted": False, "current": {"channel_id": "15", "role_id": None, "message": None}}
        assert self.delete(client, "community:1", "100", orig).json()["error"] == "conflict"
        assert notify_row(client.repo, N.TwitchLive) is not None

    def test_deleted_conflict(self, client):
        orig = {"channel_id": str(OK_CHANNEL), "role_id": None, "message": None}
        assert self.delete(client, "community:1", "100", orig).json() == {"error": "conflict", "deleted": True, "current": None}

    def test_orphan_row_can_be_edited_and_deleted(self, client):
        client.repo.session.add(
            NotifyCommunity(notify_type=N.Youtube, community_id="UCorphan", community_type=P.Google, guild_id=GUILD_ID, channel_id=OK_CHANNEL)
        )
        client.repo.session.commit()
        orig = {"channel_id": str(OK_CHANNEL), "role_id": None, "message": None}
        assert self.put(client, "community:2", "UCorphan", {"channel_id": "15"}, orig).status_code == 200
        assert self.delete(client, "community:2", "UCorphan", {**orig, "channel_id": "15"}).status_code == 200

    def test_youtube_push_failure_keeps_notify(self, client):
        client.apis.add_push_ok = False
        res = self.create(client, ["community:2"], platform="youtube", account_id=YT.id)
        assert (res.status_code, res.json()) == (200, {"ok": True, "push": "failed"})
        assert notify_row(client.repo, N.Youtube, community_id=YT.id) is not None

    def test_youtube_update_resubscribes(self, client):
        client.apis.add_push_ok = False
        self.create(client, ["community:2"], platform="youtube", account_id=YT.id)
        client.apis.add_push_ok = True
        orig = {"channel_id": str(OK_CHANNEL), "role_id": None, "message": None}
        res = self.put(client, "community:2", YT.id, {"channel_id": "15"}, orig)
        assert res.json() == {"ok": True, "push": "ok"}
        assert not client.repo.get_push_record(YT.id).is_expired

    def test_bot_not_in_guild(self, client, monkeypatch):
        monkeypatch.setattr(sclient, "bot", fake_bot(None))
        assert self.resolve(client).status_code == 404
