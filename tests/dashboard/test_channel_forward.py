"""實況主後台的轉發 Discord（W-11）：目前設定、選項、儲存與權限（真實 PostgreSQL，假 bot）。"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from starlib import sclient, twitch_audit
from starlib.database import TwitchBotJoinChannel
from starlib.identity import Account, LinkedPassport, ResolvedAccount
from starlib.twitch_audit import list_changes
from starServer.dashboard import channel_forward, channels
from tests.helpers.accounts import account
from tests.helpers.dashboard_auth import FRONTEND, USER_ID, make_app, make_domalyze_session, make_twitch_session
from tests.helpers.dashboard_guilds import MANAGE_CHANNELS, g
from tests.helpers.dashboard_notifies import GUILD_ID, NO_SEND_CHANNEL, OK_CHANNEL, VOICE_CHANNEL, fake_guild

pytestmark = pytest.mark.usefixtures("dashboard_env")

CHANNEL = 7101
OTHER_GUILD = 2002
URL = f"/dashboard/channels/{CHANNEL}/forward"
HEADERS = {"Origin": FRONTEND}


def guild(gid: int, name: str, channel_ids=(OK_CHANNEL, VOICE_CHANNEL, NO_SEND_CHANNEL, 15)):
    base = fake_guild()
    base.id = gid
    base.name = name
    base.icon = None
    base.unavailable = False
    base.channels = [base.get_channel(i) for i in channel_ids]
    known = {c.id: c for c in base.channels}
    base.get_channel = known.get
    for pos, c in enumerate(base.channels):
        c.position = pos
    return base


def fake_bot(*guilds, ready: bool = True):
    pool = ThreadPoolExecutor(max_workers=1)
    by_id = {x.id: x for x in guilds}

    def get_channel(cid):
        for owner in guilds:
            found = owner.get_channel(cid)
            if found is not None:
                found.guild = owner
                return found
        return None

    return SimpleNamespace(
        is_ready=lambda: ready,
        guilds=list(guilds),
        get_guild=by_id.get,
        get_channel=get_channel,
        submit=lambda coro: pool.submit(asyncio.run, coro),
    )


@pytest.fixture
def modules(monkeypatch, repo):
    for module in (channels, channel_forward, twitch_audit):
        monkeypatch.setattr(module, "sqldb", repo)


@pytest.fixture(autouse=True)
def _fresh_channel(repo):
    row = repo.session.get(TwitchBotJoinChannel, CHANNEL)
    if row is not None:
        repo.session.delete(row)
    repo.session.flush()


@pytest.fixture
def bot(monkeypatch):
    b = fake_bot(guild(GUILD_ID, "星羽之家"), guild(OTHER_GUILD, "別人的伺服器"))
    monkeypatch.setattr(sclient, "bot", b)
    return b


@pytest.fixture
def perms(discord_env):
    """使用者在 GUILD_ID 有 Manage Channels，在 OTHER_GUILD 只是普通成員。"""
    discord_env.guilds = [g(str(GUILD_ID), "星羽之家", MANAGE_CHANNELS), g(str(OTHER_GUILD), "別人的伺服器", 0)]
    return discord_env


def linked_account(with_discord: bool = True) -> Account:
    base = account(uuid4(), discord_ids=(int(USER_ID),) if with_discord else ())
    return replace(base, twitch_passports=(LinkedPassport(str(CHANNEL), "Host"),))


def domalyze_client(repo, dashboard_env, with_discord: bool = True) -> TestClient:
    acc = linked_account(with_discord)
    dashboard_env.directory.by_account_id[acc.account_id] = ResolvedAccount(acc)
    sid = make_domalyze_session(repo, acc.account_id, user_id=USER_ID if with_discord else None)
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False, headers=HEADERS)
    c.cookies.set("dashboard_session", sid)
    return c


def twitch_client(repo) -> TestClient:
    sid = make_twitch_session(repo, twitch_id=str(CHANNEL), login="host", name="Host")
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False, headers=HEADERS)
    c.cookies.set("dashboard_session", sid)
    return c


def row(repo) -> TwitchBotJoinChannel | None:
    repo.session.expire_all()
    return repo.session.get(TwitchBotJoinChannel, CHANNEL)


def configured(repo, channel_id=OK_CHANNEL, guild_id: int | None = GUILD_ID, state="enabled") -> None:
    repo.add(
        TwitchBotJoinChannel(twitch_id=CHANNEL, state=state, action_channel_id=channel_id, action_guild_id=guild_id)
    )


class TestGet:
    def test_not_configured(self, repo, dashboard_env, modules, bot):
        c = domalyze_client(repo, dashboard_env)
        assert c.get(URL).json() == {"editable": True, "guild": None, "channel": None}

    def test_returns_names_from_bot_cache(self, repo, dashboard_env, modules, bot):
        configured(repo)
        body = domalyze_client(repo, dashboard_env).get(URL).json()
        assert body["guild"] == {"id": str(GUILD_ID), "name": "星羽之家"}
        assert body["channel"] == {"id": str(OK_CHANNEL), "name": "general"}

    def test_legacy_row_without_guild_takes_guild_from_channel(self, repo, dashboard_env, modules, bot):
        configured(repo, guild_id=None)
        body = domalyze_client(repo, dashboard_env).get(URL).json()
        assert body["guild"] == {"id": str(GUILD_ID), "name": "星羽之家"}

    def test_bot_not_ready_returns_ids_without_names(self, repo, dashboard_env, modules, monkeypatch):
        monkeypatch.setattr(sclient, "bot", fake_bot(guild(GUILD_ID, "x"), ready=False))
        configured(repo)
        body = domalyze_client(repo, dashboard_env).get(URL).json()
        assert body["guild"] == {"id": str(GUILD_ID), "name": None}
        assert body["channel"] == {"id": str(OK_CHANNEL), "name": None}

    def test_missing_channel_keeps_id_with_null_name(self, repo, dashboard_env, modules, bot):
        configured(repo, channel_id=999)
        assert domalyze_client(repo, dashboard_env).get(URL).json()["channel"] == {"id": "999", "name": None}

    def test_twitch_login_sees_setting_but_not_editable(self, repo, modules, bot):
        configured(repo)
        body = twitch_client(repo).get(URL).json()
        assert body["editable"] is False
        assert body["channel"]["name"] == "general"

    def test_other_channel_is_forbidden(self, repo, dashboard_env, modules, bot):
        r = domalyze_client(repo, dashboard_env).get("/dashboard/channels/1/forward")
        assert (r.status_code, r.json()) == (403, {"error": "channel_forbidden"})


class TestOptions:
    def test_lists_only_guilds_with_manage_channels_and_usable_channels(self, repo, dashboard_env, modules, bot, perms):
        body = domalyze_client(repo, dashboard_env).get(f"{URL}/options").json()
        assert [x["id"] for x in body["guilds"]] == [str(GUILD_ID)]
        # 語音頻道與 bot 不能發言的頻道不列
        assert [c["id"] for c in body["guilds"][0]["channels"]] == [str(OK_CHANNEL), "15"]

    def test_excludes_guild_bot_is_not_in(self, repo, dashboard_env, modules, monkeypatch, perms):
        perms.guilds.append(g("3003", "bot 不在", MANAGE_CHANNELS))
        monkeypatch.setattr(sclient, "bot", fake_bot(guild(GUILD_ID, "星羽之家")))
        body = domalyze_client(repo, dashboard_env).get(f"{URL}/options").json()
        assert [x["id"] for x in body["guilds"]] == [str(GUILD_ID)]

    def test_twitch_login_is_forbidden(self, repo, modules, bot, perms):
        r = twitch_client(repo).get(f"{URL}/options")
        assert (r.status_code, r.json()) == (403, {"error": "forward_not_allowed"})

    def test_bot_not_ready(self, repo, dashboard_env, modules, monkeypatch, perms):
        monkeypatch.setattr(sclient, "bot", fake_bot(guild(GUILD_ID, "x"), ready=False))
        r = domalyze_client(repo, dashboard_env).get(f"{URL}/options")
        assert (r.status_code, r.json()) == (503, {"error": "bot_unavailable"})


class TestPut:
    def put(self, c: TestClient, guild_id=GUILD_ID, channel_id=OK_CHANNEL):
        return c.put(URL, json={"guild_id": guild_id, "channel_id": channel_id})

    def test_saves_and_records_create(self, repo, dashboard_env, modules, bot, perms):
        r = self.put(domalyze_client(repo, dashboard_env))
        assert r.status_code == 200
        assert r.json()["channel"] == {"id": str(OK_CHANNEL), "name": "general"}
        saved = row(repo)
        assert (saved.action_channel_id, saved.action_guild_id, saved.state) == (OK_CHANNEL, GUILD_ID, "inactive")
        (entry,) = list_changes(CHANNEL)
        assert (entry.target_kind, entry.target_key, entry.action, entry.source) == (
            "forward",
            "discord",
            "create",
            "dashboard",
        )
        assert (entry.actor.platform, entry.actor.id) == ("discord", USER_ID)
        assert entry.before is None
        assert entry.after == {"guild_id": str(GUILD_ID), "channel_id": str(OK_CHANNEL)}

    def test_update_records_before_and_after(self, repo, dashboard_env, modules, bot, perms):
        configured(repo, channel_id=99)
        self.put(domalyze_client(repo, dashboard_env), channel_id=15)
        assert row(repo).state == "enabled"
        (entry,) = list_changes(CHANNEL)
        assert entry.action == "update"
        assert entry.before == {"guild_id": str(GUILD_ID), "channel_id": "99"}
        assert entry.after == {"guild_id": str(GUILD_ID), "channel_id": "15"}

    def test_clear(self, repo, dashboard_env, modules, bot, perms):
        configured(repo)
        r = domalyze_client(repo, dashboard_env).put(URL, json={"guild_id": None, "channel_id": None})
        assert r.json() == {"editable": True, "guild": None, "channel": None}
        saved = row(repo)
        assert (saved.action_channel_id, saved.action_guild_id) == (None, None)
        (entry,) = list_changes(CHANNEL)
        assert (entry.action, entry.after) == ("delete", None)

    def test_clear_works_after_bot_left_guild(self, repo, dashboard_env, modules, monkeypatch, perms):
        monkeypatch.setattr(sclient, "bot", fake_bot())
        configured(repo)
        r = domalyze_client(repo, dashboard_env).put(URL, json={"guild_id": None, "channel_id": None})
        assert r.status_code == 200 and row(repo).action_channel_id is None

    def test_unchanged_writes_nothing(self, repo, dashboard_env, modules, bot, perms):
        configured(repo)
        assert self.put(domalyze_client(repo, dashboard_env)).status_code == 200
        assert list_changes(CHANNEL) == []

    def test_no_manage_channels_is_403(self, repo, dashboard_env, modules, bot, perms):
        r = self.put(domalyze_client(repo, dashboard_env), guild_id=OTHER_GUILD)
        assert (r.status_code, r.json()) == (403, {"error": "forward_forbidden"})
        assert row(repo).action_channel_id is None and list_changes(CHANNEL) == []

    def test_channel_of_another_guild_is_rejected(self, repo, dashboard_env, modules, monkeypatch, perms):
        # OK_CHANNEL 只存在於使用者沒有權限的伺服器
        mine = guild(GUILD_ID, "星羽之家", channel_ids=(15,))
        other = guild(OTHER_GUILD, "別人的伺服器", channel_ids=(OK_CHANNEL,))
        monkeypatch.setattr(sclient, "bot", fake_bot(mine, other))
        r = self.put(domalyze_client(repo, dashboard_env))
        assert (r.status_code, r.json()) == (400, {"error": "invalid_channel"})
        assert row(repo).action_channel_id is None

    @pytest.mark.parametrize("channel_id", [VOICE_CHANNEL, NO_SEND_CHANNEL, 424242])
    def test_unusable_channel_is_400(self, repo, dashboard_env, modules, bot, perms, channel_id):
        r = self.put(domalyze_client(repo, dashboard_env), channel_id=channel_id)
        assert (r.status_code, r.json()) == (400, {"error": "invalid_channel"})

    def test_bot_not_in_guild_is_404(self, repo, dashboard_env, modules, monkeypatch, perms):
        monkeypatch.setattr(sclient, "bot", fake_bot())
        r = self.put(domalyze_client(repo, dashboard_env))
        assert (r.status_code, r.json()) == (404, {"error": "bot_not_in_guild"})

    def test_channel_without_guild_is_invalid_request(self, repo, dashboard_env, modules, bot, perms):
        r = domalyze_client(repo, dashboard_env).put(URL, json={"guild_id": None, "channel_id": OK_CHANNEL})
        assert (r.status_code, r.json()) == (400, {"error": "invalid_request"})

    def test_twitch_login_cannot_edit(self, repo, modules, bot, perms):
        r = self.put(twitch_client(repo))
        assert (r.status_code, r.json()) == (403, {"error": "forward_not_allowed"})
        assert row(repo) is None

    def test_domalyze_without_discord_cannot_edit(self, repo, dashboard_env, modules, bot, perms):
        r = self.put(domalyze_client(repo, dashboard_env, with_discord=False))
        assert r.status_code == 403

    def test_other_channel_is_forbidden(self, repo, dashboard_env, modules, bot, perms):
        c = domalyze_client(repo, dashboard_env)
        r = c.put("/dashboard/channels/1/forward", json={"guild_id": None, "channel_id": None})
        assert (r.status_code, r.json()) == (403, {"error": "channel_forbidden"})
