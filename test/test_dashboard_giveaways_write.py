"""伺服器管理後台 G-02：提前結束與重抽（假 Discord，真實 PostgreSQL）。"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import discord
import pytest
from fastapi.testclient import TestClient
from test_dashboard_auth import FRONTEND, dashboard_env, make_app, make_session  # noqa: F401  (fixture 與 helper)
from test_dashboard_giveaways import CREATOR, LEFT, MEMBER, FakeGuild, add_giveaway, join
from test_dashboard_guilds import MANAGE_CHANNELS, MANAGE_MESSAGES, g, seed_token
from test_dashboard_guilds import discord as discord_env  # noqa: F401  (fixture)
from test_dashboard_notifies import GUILD_ID
from test_identity import repo  # noqa: F401

from starDiscord.uiElement.view import GiveawayView
from starlib import sclient
from starlib.database import Giveaway
from starServer.dashboard import giveaways

URL = f"/dashboard/guilds/{GUILD_ID}/giveaways"


def http_error(cls, status: int, text: str = "error"):
    return cls(SimpleNamespace(status=status, reason=text), text)


class FakeMessage:
    def __init__(self, reply_error: Exception | None = None):
        self.edits: list[dict] = []
        self.replies: list[str] = []
        self.reply_error = reply_error

    async def edit(self, **kwargs):
        self.edits.append(kwargs)

    async def reply(self, content, **kwargs):
        if self.reply_error is not None:
            raise self.reply_error
        self.replies.append(content)


class FakeChannel:
    def __init__(
        self,
        message: FakeMessage | None,
        send_error: Exception | None = None,
        fetch_error: Exception | None = None,
    ):
        self.message = message
        self.send_error = send_error
        self.fetch_error = fetch_error
        self.sent: list[str] = []

    async def fetch_message(self, mid: int):
        if self.fetch_error is not None:
            raise self.fetch_error
        if self.message is None:
            raise http_error(discord.NotFound, 404, "Unknown Message")
        return self.message

    async def send(self, content, **kwargs):
        if self.send_error is not None:
            raise self.send_error
        self.sent.append(content)


class FakeBot:
    def __init__(self, guild: FakeGuild):
        self.guild = guild
        self.channel: FakeChannel | None = FakeChannel(FakeMessage())
        self.removed_jobs: list[str] = []
        self.scheduler = SimpleNamespace(remove_job=self.removed_jobs.append)
        self._pool = ThreadPoolExecutor(max_workers=1)

    def is_ready(self) -> bool:
        return True

    def get_guild(self, gid: int):
        return self.guild if gid == GUILD_ID else None

    def submit(self, coro):
        return self._pool.submit(asyncio.run, coro)

    def get_user(self, uid: int):
        return None

    def get_channel(self, cid: int):
        return self.channel

    async def fetch_channel(self, cid: int):
        raise http_error(discord.NotFound, 404, "Unknown Channel")


@pytest.fixture
def client(discord_env, repo, dashboard_env, monkeypatch) -> TestClient:  # noqa: F811
    seed_token(repo, dashboard_env.credential_id)
    make_session(repo)
    discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_MESSAGES)]
    monkeypatch.setattr(giveaways, "sqldb", repo)
    bot = FakeBot(FakeGuild())
    monkeypatch.setattr(sclient, "bot", bot)
    c = TestClient(make_app(), base_url="https://testserver", follow_redirects=False)
    c.cookies.set("dashboard_session", "sid")
    c.repo = repo  # pyright: ignore[reportAttributeAccessIssue]
    c.discord_env = discord_env  # pyright: ignore[reportAttributeAccessIssue]
    c.bot = bot  # pyright: ignore[reportAttributeAccessIssue]
    return c


def post(client, giveaway_id: int, action: str, body: dict | None = None):
    return client.post(f"{URL}/{giveaway_id}/{action}", json=body or {}, headers={"Origin": FRONTEND})


def winners_of(client, giveaway_id: int) -> set[int]:
    client.repo.session.expire_all()
    return {u.user_id for u in client.repo.get_giveaway_users(giveaway_id) if u.is_winner}


def stored(client, giveaway_id: int) -> Giveaway:
    client.repo.session.expire_all()
    return client.repo.get_giveaway(giveaway_id)


def active_with_joiners(client, joiners=(MEMBER, LEFT)) -> Giveaway:
    gw = add_giveaway(client, is_on=True)
    for uid in joiners:
        join(client, gw.id, uid)
    return gw


def ended_with_winner(client, winner=MEMBER, others=(LEFT, CREATOR)) -> Giveaway:
    gw = add_giveaway(client)
    join(client, gw.id, winner, winner=True)
    for uid in others:
        join(client, gw.id, uid)
    return gw


class TestEnd:
    def test_ends_edits_message_and_replies(self, client):
        gw = active_with_joiners(client)
        message = client.bot.channel.message
        r = post(client, gw.id, "end")
        assert r.status_code == 200
        assert r.json() == {
            "status": "ok",
            "announce_failure": None,
            "announce_failure_text": None,
            "no_replacement": False,
        }
        assert stored(client, gw.id).is_on is False
        assert len(winners_of(client, gw.id)) == 1
        assert len(message.edits) == 1
        assert "embed" in message.edits[0]
        assert len(message.replies) == 1
        assert "恭喜" in message.replies[0]
        assert f"giveaway_end_{gw.id}" in client.bot.removed_jobs

    def test_message_deleted_sends_plain_message(self, client):
        gw = active_with_joiners(client)
        client.bot.channel = FakeChannel(None)
        r = post(client, gw.id, "end")
        assert r.json()["status"] == "ok"
        assert r.json()["announce_failure"] is None
        assert len(client.bot.channel.sent) == 1
        assert len(winners_of(client, gw.id)) == 1

    def test_channel_missing_still_draws(self, client):
        gw = active_with_joiners(client)
        client.bot.channel = None
        r = post(client, gw.id, "end").json()
        assert r["status"] == "ok"
        assert r["announce_failure"] == "channel_missing"
        assert r["announce_failure_text"]
        assert len(winners_of(client, gw.id)) == 1

    def test_no_send_permission_still_draws(self, client):
        gw = active_with_joiners(client)
        client.bot.channel = FakeChannel(None, send_error=http_error(discord.Forbidden, 403, "Missing Permissions"))
        r = post(client, gw.id, "end").json()
        assert r["status"] == "ok"
        assert r["announce_failure"] == "no_permission"
        assert len(winners_of(client, gw.id)) == 1

    def test_already_ended_is_success_without_second_draw(self, client):
        gw = ended_with_winner(client)
        message = client.bot.channel.message
        r = post(client, gw.id, "end")
        assert r.status_code == 200
        assert r.json()["status"] == "already_ended"
        assert message.edits == [] and message.replies == []
        assert winners_of(client, gw.id) == {MEMBER}

    def test_other_guild_is_404(self, client):
        gw = add_giveaway(client, guild_id=GUILD_ID + 1, is_on=True)
        r = post(client, gw.id, "end")
        assert r.status_code == 404
        assert r.json()["error"] == "giveaway_not_found"

    def test_requires_manage_messages(self, client):
        gw = active_with_joiners(client)
        client.discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_CHANNELS)]
        assert post(client, gw.id, "end").status_code == 403
        assert stored(client, gw.id).is_on is True


class TestRedraw:
    def test_whole_batch(self, client):
        gw = ended_with_winner(client, others=(LEFT,))
        message = client.bot.channel.message
        r = post(client, gw.id, "redraw")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert r.json()["no_replacement"] is False
        assert stored(client, gw.id).redraw_count == 1
        assert len(winners_of(client, gw.id)) == 1
        assert len(message.edits) == 1 and len(message.replies) == 1
        assert "重新抽獎" in message.replies[0]

    def test_specific_winner_including_left_member(self, client):
        # 中獎者 LEFT 已離開伺服器，仍可指定取消資格，替補從其他參加者抽出
        gw = ended_with_winner(client, winner=LEFT, others=(MEMBER,))
        message = client.bot.channel.message
        r = post(client, gw.id, "redraw", {"winner_user_id": str(LEFT)})
        assert r.status_code == 200
        assert winners_of(client, gw.id) == {MEMBER}
        assert stored(client, gw.id).redraw_count == 1
        assert f"<@{MEMBER}>" in message.replies[0]
        assert len(message.edits) == 1

    def test_no_replacement_tells_admin(self, client):
        # 只有一位參加者且已是中獎者：取消資格後沒有人可替補
        gw = ended_with_winner(client, winner=MEMBER, others=())
        message = client.bot.channel.message
        r = post(client, gw.id, "redraw", {"winner_user_id": str(MEMBER)}).json()
        assert r["status"] == "ok"
        assert r["no_replacement"] is True
        assert winners_of(client, gw.id) == set()
        assert stored(client, gw.id).redraw_count == 1
        assert "沒有可替補" in message.replies[0]

    def test_message_deleted_sends_plain_message(self, client):
        gw = ended_with_winner(client)
        client.bot.channel = FakeChannel(None)
        assert post(client, gw.id, "redraw").json()["announce_failure"] is None
        assert len(client.bot.channel.sent) == 1

    def test_fetch_message_forbidden_does_not_send_plain(self, client):
        gw = ended_with_winner(client)
        channel = FakeChannel(FakeMessage(), fetch_error=http_error(discord.Forbidden, 403, "Missing Access"))
        client.bot.channel = channel
        r = post(client, gw.id, "redraw").json()
        assert r["announce_failure"] == "no_permission"
        assert channel.sent == []
        assert stored(client, gw.id).redraw_count == 1

    def test_reply_forbidden_still_redraws(self, client):
        gw = ended_with_winner(client)
        client.bot.channel = FakeChannel(FakeMessage(reply_error=http_error(discord.Forbidden, 403)))
        r = post(client, gw.id, "redraw").json()
        assert r["announce_failure"] == "no_permission"
        assert stored(client, gw.id).redraw_count == 1

    def test_not_ended_is_409(self, client):
        gw = active_with_joiners(client)
        r = post(client, gw.id, "redraw")
        assert r.status_code == 409
        assert r.json()["error"] == "giveaway_not_ended"

    def test_target_not_winner_is_409(self, client):
        gw = ended_with_winner(client)
        r = post(client, gw.id, "redraw", {"winner_user_id": LEFT})
        assert r.status_code == 409
        assert r.json()["error"] == "not_winner"

    def test_target_not_participant_is_409(self, client):
        gw = ended_with_winner(client)
        r = post(client, gw.id, "redraw", {"winner_user_id": 123456})
        assert r.status_code == 409
        assert r.json()["error"] == "not_participant"

    def test_other_guild_is_404(self, client):
        gw = add_giveaway(client, guild_id=GUILD_ID + 1)
        assert post(client, gw.id, "redraw").status_code == 404

    def test_requires_manage_messages(self, client):
        gw = ended_with_winner(client)
        client.discord_env.guilds = [g(str(GUILD_ID), "guild", MANAGE_CHANNELS)]
        assert post(client, gw.id, "redraw").status_code == 403


class TestNoDoubleDraw:
    """到期自動開獎與後台提前結束同時發生：只開獎一次，且各自看到最新狀態。"""

    def test_concurrent_finish_draws_once(self, client):
        gw = active_with_joiners(client)
        message = client.bot.channel.message
        bot = client.bot

        async def go():
            a = GiveawayView(client.repo.get_giveaway(gw.id), client.repo, bot)
            b = GiveawayView(client.repo.get_giveaway(gw.id), client.repo, bot)
            return await asyncio.gather(a.finish(), b.finish())

        outcomes = asyncio.run(go())
        assert sorted(o.status for o in outcomes) == ["already_ended", "ok"]
        assert len(message.replies) == 1
        assert len(winners_of(client, gw.id)) == 1

    def test_stale_instance_does_not_draw_again(self, client):
        gw = active_with_joiners(client)
        message = client.bot.channel.message
        bot = client.bot
        # 排程 job 持有的是尚未結束時的舊 instance（transient copy，is_on 仍是 True）
        stale = Giveaway(**{c.name: getattr(gw, c.name) for c in Giveaway.__table__.columns})
        stale.is_on = True

        async def go():
            first = await GiveawayView(client.repo.get_giveaway(gw.id), client.repo, bot).finish()
            second = await GiveawayView(stale, client.repo, bot).finish()
            return first, second

        first, second = asyncio.run(go())
        assert (first.status, second.status) == ("ok", "already_ended")
        assert len(message.replies) == 1
        assert len(winners_of(client, gw.id)) == 1

    def test_concurrent_redraw_is_serialized(self, client):
        gw = ended_with_winner(client, others=(LEFT, CREATOR))
        bot = client.bot

        async def go():
            views = [GiveawayView(client.repo.get_giveaway(gw.id), client.repo, bot) for _ in range(2)]
            return await asyncio.gather(*(v.redraw() for v in views))

        asyncio.run(go())
        # 兩次重抽依序執行，次數正確累加，中獎人數維持設定值
        assert stored(client, gw.id).redraw_count == 2
        assert len(winners_of(client, gw.id)) == 1


class TestRedrawCommand:
    """`/giveaway redraw`：回覆抽獎訊息公告並更新結果，下指令的人只收到自己看得到的完成提示。"""

    def run(self, client, monkeypatch, giveaway_id: int, winner_id: int | None = None, author_id: int = CREATOR):
        from starDiscord.cmds import command as command_cog

        cls = next(v for v in vars(command_cog).values() if isinstance(v, type) and "giveaway" in vars(v))
        monkeypatch.setattr(command_cog, "sclient", SimpleNamespace(sqldb=client.repo))

        async def is_owner(_user):
            return False

        bot = client.bot
        bot.is_owner = is_owner
        cog = cls(bot)
        responses: list[tuple] = []
        defers: list[dict] = []

        class Ctx:
            author = SimpleNamespace(id=author_id)

            async def defer(self, **kwargs):
                defers.append(kwargs)

            async def respond(self, content=None, **kwargs):
                responses.append((content, kwargs))

        winner = SimpleNamespace(id=winner_id) if winner_id else None
        asyncio.run(cls.redraw.callback(cog, Ctx(), giveaway_id, winner))
        return responses, defers

    def test_replies_on_original_message_and_confirms_privately(self, client, monkeypatch):
        gw = ended_with_winner(client, others=(LEFT,))
        message = client.bot.channel.message
        responses, defers = self.run(client, monkeypatch, gw.id)
        assert defers == [{"ephemeral": True}]
        assert len(responses) == 1
        assert "已重新抽獎" in responses[0][0]
        assert "沒有可替補" not in responses[0][0]
        assert len(message.replies) == 1 and len(message.edits) == 1
        assert stored(client, gw.id).redraw_count == 1

    def test_reports_missing_announcement(self, client, monkeypatch):
        gw = ended_with_winner(client)
        client.bot.channel = None
        responses, _ = self.run(client, monkeypatch, gw.id)
        assert "已重新抽獎，但" in responses[0][0]
        assert stored(client, gw.id).redraw_count == 1

    def test_reports_no_replacement(self, client, monkeypatch):
        gw = ended_with_winner(client, winner=MEMBER, others=())
        responses, _ = self.run(client, monkeypatch, gw.id, winner_id=MEMBER)
        assert responses[0][0] == "已重新抽獎，但沒有可替補的參加者"
        assert winners_of(client, gw.id) == set()
        assert stored(client, gw.id).redraw_count == 1

    def test_only_creator(self, client, monkeypatch):
        gw = ended_with_winner(client)
        responses, _ = self.run(client, monkeypatch, gw.id, author_id=999)
        assert "不是此抽獎的發起人" in responses[0][0]
        assert stored(client, gw.id).redraw_count == 0
