"""伺服器管理後台 V-03：後台發起投票（假 Discord，真實 PostgreSQL）。"""

from __future__ import annotations

from types import SimpleNamespace

import discord
import pytest
from fastapi.testclient import TestClient
from sqlmodel import select
from test_dashboard_auth import USER_ID, dashboard_env, make_app, make_session  # noqa: F401  (fixture 與 helper)
from test_dashboard_guilds import MANAGE_CHANNELS, MANAGE_MESSAGES, g
from test_dashboard_guilds import discord as discord_env  # noqa: F401  (fixture)
from test_dashboard_notifies import GUILD_ID
from test_dashboard_polls import FakeBot
from test_identity import repo  # noqa: F401

from starDiscord.uiElement import view as view_module
from starlib import sclient
from starlib.database import Poll

URL = f"/dashboard/guilds/{GUILD_ID}/polls"
OPERATOR = int(USER_ID)
HEADERS = {"Origin": "https://domalyze.net"}

OK = discord.Permissions(view_channel=True, send_messages=True)
MUTE = discord.Permissions(view_channel=True)


class FakeChannel:
    def __init__(self, cid: int, name: str, bot_perms=OK, operator_perms=OK, type=discord.ChannelType.text, position=0):
        self.id = cid
        self.name = name
        self.type = type
        self.position = position
        self.category = None
        self.bot_perms = bot_perms
        self.operator_perms = operator_perms
        self.sent: list[dict] = []
        self.send_error: Exception | None = None

    def permissions_for(self, member):
        return self.bot_perms if member.is_bot else self.operator_perms

    async def send(self, **kwargs):
        if self.send_error is not None:
            raise self.send_error
        self.sent.append(kwargs)
        return SimpleNamespace(id=9000 + len(self.sent))


def make_role(rid: int, name: str, position: int, *, default=False, managed=False):
    return SimpleNamespace(
        id=rid,
        name=name,
        position=position,
        managed=managed,
        color=SimpleNamespace(value=0xFF0000),
        is_default=lambda: default,
        mention=f"<@&{rid}>",
    )


class FakeGuild:
    def __init__(self):
        self.id = GUILD_ID
        self.unavailable = False
        self.me = SimpleNamespace(is_bot=True, display_name="bot")
        self.operator = SimpleNamespace(
            is_bot=False,
            id=OPERATOR,
            name="管理員",
            display_name="管理員",
            display_avatar=SimpleNamespace(url="https://cdn.example/a.png"),
        )
        self.channels = {
            500: FakeChannel(500, "一般", position=1),
            501: FakeChannel(501, "公告", type=discord.ChannelType.news, position=2),
            502: FakeChannel(502, "bot 不能發言", bot_perms=MUTE, position=3),
            503: FakeChannel(503, "你不能發言", operator_perms=MUTE, position=4),
            504: FakeChannel(504, "語音", type=discord.ChannelType.voice, position=5),
        }
        self.roles = [
            make_role(GUILD_ID, "@everyone", 0, default=True),
            make_role(600, "成員", 2),
            make_role(601, "整合", 3, managed=True),
            make_role(602, "VIP", 5),
        ]
        self.in_guild = True

    @property
    def text_channels(self):
        return [c for c in self.channels.values() if c.type in (discord.ChannelType.text, discord.ChannelType.news)]

    def get_member(self, uid: int):
        return self.operator if self.in_guild and uid == OPERATOR else None

    def get_role(self, rid: int):
        return next((r for r in self.roles if r.id == rid), None)

    def get_channel(self, cid: int):
        return self.channels.get(cid)


@pytest.fixture
def client(discord_env, repo, dashboard_env, monkeypatch) -> TestClient:  # noqa: F811
    make_session(repo)
    discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_MESSAGES)]
    monkeypatch.setattr(view_module, "sqldb", repo)
    guild = FakeGuild()
    monkeypatch.setattr(sclient, "bot", FakeBot(guild))
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
    c.cookies.set("dashboard_session", "sid")
    c.guild = guild  # pyright: ignore[reportAttributeAccessIssue]
    c.repo = repo  # pyright: ignore[reportAttributeAccessIssue]
    c.discord_env = discord_env  # pyright: ignore[reportAttributeAccessIssue]
    c.before = poll_count(c)  # pyright: ignore[reportAttributeAccessIssue]
    return c


def post(client, **overrides):
    data = {"channel_id": "500", "title": "午餐吃什麼", "options": ["拉麵", "咖哩"]}
    data.update(overrides)
    return client.post(URL, json=data, headers=HEADERS)


def poll_count(client) -> int:
    client.repo.session.expire_all()
    return len(client.repo.session.exec(select(Poll)).all())


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
        ("cls", "status", "code"),
        [
            (discord.Forbidden, 403, "no_permission"),
            (discord.NotFound, 404, "channel_missing"),
            (discord.HTTPException, 500, "failed"),
        ],
    )
    def test_send_failure_creates_nothing(self, client, cls, status, code):
        client.guild.channels[500].send_error = cls(SimpleNamespace(status=status, reason=""), "")
        r = post(client)
        assert r.status_code == 400
        assert r.json() == {
            "error": "poll_send_failed",
            "message_failure": code,
            "message_failure_text": view_module.MESSAGE_FAILURE_TEXT[code],
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
