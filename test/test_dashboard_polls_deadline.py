"""投票截止時間 V-04：排程、自動結算、訊息顯示（假 Discord 與假 scheduler，真實 PostgreSQL）。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from apscheduler.jobstores.base import JobLookupError
from test_dashboard_auth import dashboard_env  # noqa: F401
from test_dashboard_guilds import discord as discord_env  # noqa: F401
from test_dashboard_polls_core import (  # noqa: F401
    CHANNEL_ID,
    GUILD_ID,
    FakeBot,
    FakeChannel,
    FakeMessage,
    add_poll,
    fake_chart,
    http_error,
    stored,
)
from test_dashboard_polls_create import HEADERS, URL, client, poll_count, post  # noqa: F401
from test_identity import repo  # noqa: F401

from starDiscord.cmds import bot_event
from starDiscord.cmds import command as cmd
from starDiscord.uiElement.view import PollView
from starlib import sclient
from starlib.utils import nowtz


class FakeScheduler:
    def __init__(self):
        self.jobs: dict[str, dict] = {}

    def add_job(self, func, trigger, id, replace_existing=False):
        self.jobs[id] = {"func": func, "run_at": trigger.run_date}

    def remove_job(self, job_id):
        if job_id not in self.jobs:
            raise JobLookupError(job_id)
        del self.jobs[job_id]


class SchedBot(FakeBot):
    def __init__(self, channel: FakeChannel | None):
        super().__init__(channel)
        self.scheduler = FakeScheduler()


def build(poll, repo, bot) -> PollView:  # noqa: F811
    """discord.ui.View 建立時需要執行中的 event loop"""

    async def make():
        return PollView(poll, repo, bot)  # type: ignore[arg-type]

    return asyncio.run(make())


def with_deadline(repo, poll, delta: timedelta):  # noqa: F811
    poll.deadline = (nowtz() + delta).replace(microsecond=0)
    return repo.merge(poll)


class TestSchedule:
    def test_future_deadline_scheduled_at_deadline(self, repo):  # noqa: F811
        poll = with_deadline(repo, add_poll(repo), timedelta(hours=1))
        bot = SchedBot(None)
        build(poll, repo, bot).schedule_end()  # type: ignore[arg-type]
        assert bot.scheduler.jobs[f"poll_end_{poll.poll_id}"]["run_at"] == poll.deadline

    def test_expired_deadline_scheduled_in_10_seconds(self, repo):  # noqa: F811
        poll = with_deadline(repo, add_poll(repo), timedelta(hours=-1))
        bot = SchedBot(None)
        before = nowtz()
        build(poll, repo, bot).schedule_end()  # type: ignore[arg-type]
        run_at = bot.scheduler.jobs[f"poll_end_{poll.poll_id}"]["run_at"]
        assert before + timedelta(seconds=9) <= run_at <= nowtz() + timedelta(seconds=10)

    def test_no_deadline_not_scheduled(self, repo):  # noqa: F811
        bot = SchedBot(None)
        build(add_poll(repo), repo, bot).schedule_end()  # type: ignore[arg-type]
        assert bot.scheduler.jobs == {}


class TestAutoEnd:
    def test_auto_end_finishes_and_updates_message(self, repo):  # noqa: F811
        message = FakeMessage()
        poll = with_deadline(repo, add_poll(repo), timedelta(minutes=2))
        bot = SchedBot(FakeChannel(message))
        view = build(poll, repo, bot)
        view.schedule_end()
        asyncio.run(bot.scheduler.jobs[f"poll_end_{poll.poll_id}"]["func"]())
        row = stored(repo, poll.poll_id)
        assert row.end_at is not None
        assert row.message_failure is None
        assert len(message.edits) == 1
        assert bot.scheduler.jobs == {}

    def test_deleted_message_still_ends_with_failure(self, repo):  # noqa: F811
        poll = with_deadline(repo, add_poll(repo), timedelta(minutes=2))
        bot = SchedBot(FakeChannel(None))
        asyncio.run(build(poll, repo, bot).auto_end())  # type: ignore[arg-type]
        row = stored(repo, poll.poll_id)
        assert row.end_at is not None
        assert row.message_failure == "message_missing"

    def test_manual_finish_removes_job_and_auto_end_does_nothing(self, repo):  # noqa: F811
        message = FakeMessage()
        poll = with_deadline(repo, add_poll(repo), timedelta(minutes=2))
        bot = SchedBot(FakeChannel(message))
        view = build(poll, repo, bot)
        view.schedule_end()
        job_func = bot.scheduler.jobs[f"poll_end_{poll.poll_id}"]["func"]

        async def go():
            assert (await view.finish()).status == "ok"
            assert bot.scheduler.jobs == {}
            await job_func()  # 假設 job 已在執行中才被移除

        asyncio.run(go())
        assert len(message.edits) == 1

    def test_auto_end_of_deleted_poll_is_logged_not_raised(self, repo):  # noqa: F811
        poll = with_deadline(repo, add_poll(repo), timedelta(minutes=2))
        bot = SchedBot(FakeChannel(FakeMessage()))
        view = build(poll, repo, bot)
        repo.delete_poll(poll.poll_id)
        asyncio.run(view.auto_end())


class TestEmbed:
    def make_view(self, repo, deadline):  # noqa: F811
        poll = add_poll(repo)
        if deadline:
            poll = with_deadline(repo, poll, deadline)
        return build(poll, repo, SchedBot(None)), poll  # type: ignore[arg-type]

    def test_embed_shows_deadline(self, repo):  # noqa: F811
        view, poll = self.make_view(repo, timedelta(minutes=2))
        embed = view.embed(FakeBot(None).guild)  # type: ignore[arg-type]
        ts = int(poll.deadline.timestamp())
        assert f"截止時間：<t:{ts}:f>（<t:{ts}:R>）" in embed.description

    def test_embed_without_deadline(self, repo):  # noqa: F811
        view, _ = self.make_view(repo, None)
        assert "截止時間" not in view.embed(FakeBot(None).guild).description  # type: ignore[arg-type]


class LoadBot(SchedBot):
    def __init__(self, channel: FakeChannel | None):
        super().__init__(channel)
        self.views: list[PollView] = []

    def add_view(self, view, message_id=None):
        self.views.append(view)


def run_load(repo, bot):  # noqa: F811
    async def go():
        bot_event.load_poll_views(bot, repo, nowtz())
        await asyncio.sleep(0.2)  # 讓 create_task 的結算跑完

    asyncio.run(go())


class TestStartupLoad:
    def test_expired_deadline_is_rescheduled_for_catch_up(self, repo):  # noqa: F811
        poll = with_deadline(repo, add_poll(repo), timedelta(hours=-3))
        bot = LoadBot(FakeChannel(FakeMessage()))
        run_load(repo, bot)
        assert len(bot.views) == 1
        run_at = bot.scheduler.jobs[f"poll_end_{poll.poll_id}"]["run_at"]
        assert run_at > nowtz()
        assert stored(repo, poll.poll_id).end_at is None

    def test_future_deadline_is_rescheduled_at_deadline(self, repo):  # noqa: F811
        poll = with_deadline(repo, add_poll(repo), timedelta(hours=3))
        bot = LoadBot(None)
        run_load(repo, bot)
        assert bot.scheduler.jobs[f"poll_end_{poll.poll_id}"]["run_at"] == poll.deadline

    def test_catch_up_job_ends_poll(self, repo):  # noqa: F811
        message = FakeMessage()
        poll = with_deadline(repo, add_poll(repo), timedelta(hours=-3))
        bot = LoadBot(FakeChannel(message))
        run_load(repo, bot)
        asyncio.run(bot.scheduler.jobs[f"poll_end_{poll.poll_id}"]["func"]())
        assert stored(repo, poll.poll_id).end_at is not None
        assert len(message.edits) == 1

    def test_poll_with_deadline_skips_30_day_rule(self, repo):  # noqa: F811
        poll = with_deadline(repo, add_poll(repo, created_days_ago=31), timedelta(hours=3))
        bot = LoadBot(FakeChannel(FakeMessage()))
        run_load(repo, bot)
        assert stored(repo, poll.poll_id).end_at is None
        assert len(bot.views) == 1

    def test_30_day_rule_still_ends_poll_without_deadline(self, repo):  # noqa: F811
        old = add_poll(repo, created_days_ago=31)
        recent = add_poll(repo, created_days_ago=29)
        bot = LoadBot(FakeChannel(FakeMessage()))
        run_load(repo, bot)
        assert stored(repo, old.poll_id).end_at is not None
        assert stored(repo, recent.poll_id).end_at is None
        assert len(bot.views) == 1
        assert bot.scheduler.jobs == {}


class TestCreateCommand:
    """`/poll create` 的截止時間選項：解析、驗證、傳給 create_and_send"""

    @pytest.fixture
    def env(self, monkeypatch):
        send = AsyncMock()
        monkeypatch.setattr(cmd.PollView, "create_and_send", send)
        ctx = MagicMock()
        ctx.guild.id = GUILD_ID
        ctx.channel_id = CHANNEL_ID
        ctx.author.id = 7001
        ctx.respond = AsyncMock()
        return SimpleNamespace(ctx=ctx, send=send, cog=cmd.command(MagicMock()))

    def call(self, env, end_time):
        asyncio.run(
            env.cog.create_poll.callback(env.cog, env.ctx, "標題", "甲,乙", False, True, False, False, 1, None, None, end_time)
        )

    def error_text(self, env) -> str:
        env.send.assert_not_called()
        [call] = env.ctx.respond.call_args_list
        assert call.kwargs["ephemeral"] is True
        return call.args[0]

    def test_duration_is_passed_as_deadline(self, env):
        before = nowtz()
        self.call(env, "2m")
        deadline = env.send.call_args.kwargs["deadline"]
        assert timedelta(seconds=60) < deadline - before <= timedelta(seconds=121)
        assert deadline.microsecond == 0

    def test_no_end_time_means_no_deadline(self, env):
        self.call(env, None)
        assert env.send.call_args.kwargs["deadline"] is None

    def test_absolute_datetime_is_accepted(self, env):
        target = (nowtz() + timedelta(days=2)).replace(second=0, microsecond=0)
        self.call(env, target.strftime("%Y-%m-%d %H:%M"))
        assert env.send.call_args.kwargs["deadline"] == target

    def test_unparsable_is_rejected(self, env):
        self.call(env, "亂打一通")
        assert "無法辨認截止時間" in self.error_text(env)

    @pytest.mark.parametrize("text", ["30s", "59秒"])
    def test_under_one_minute_is_rejected(self, env, text):
        self.call(env, text)
        assert "截止時間至少要在 1 分鐘後" in self.error_text(env)

    def test_past_time_is_rejected(self, env):
        self.call(env, (nowtz() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M"))
        assert "截止時間至少要在 1 分鐘後" in self.error_text(env)

    def test_over_30_days_is_rejected(self, env):
        self.call(env, "31d")
        assert "截止時間最長為 30 天後" in self.error_text(env)


class TestDashboardCreate:
    """後台發起帶 deadline：驗證、存入、排程"""

    @pytest.fixture
    def api(self, client):
        client.scheduler = FakeScheduler()
        sclient.bot.scheduler = client.scheduler  # type: ignore[union-attr]
        return client

    def future(self, **delta) -> datetime:
        return nowtz() + timedelta(**delta)

    def test_deadline_is_saved_and_scheduled(self, api):
        deadline = self.future(hours=2).replace(microsecond=0)
        r = post(api, deadline=deadline.isoformat())
        assert r.status_code == 200, r.text
        poll_id = r.json()["poll_id"]
        api.repo.session.expire_all()
        assert api.repo.get_poll(poll_id).deadline == deadline
        assert api.scheduler.jobs[f"poll_end_{poll_id}"]["run_at"] == deadline
        embed = api.guild.channels[500].sent[0]["embed"]
        assert f"<t:{int(deadline.timestamp())}:f>" in embed.description

    @pytest.mark.parametrize("value", [None, "omit"])
    def test_without_deadline(self, api, value):
        r = post(api) if value == "omit" else post(api, deadline=None)
        assert r.status_code == 200
        api.repo.session.expire_all()
        assert api.repo.get_poll(r.json()["poll_id"]).deadline is None
        assert api.scheduler.jobs == {}

    @pytest.mark.parametrize(
        ("deadline", "reason"),
        [
            (lambda: (nowtz() - timedelta(minutes=5)).isoformat(), "截止時間必須晚於現在"),
            (lambda: (nowtz() + timedelta(days=30, minutes=2)).isoformat(), "截止時間最長為 30 天後"),
            (lambda: (nowtz() + timedelta(hours=1)).replace(tzinfo=None).isoformat(), "截止時間必須包含時區"),
        ],
    )
    def test_invalid_deadline_is_rejected(self, api, deadline, reason):
        r = post(api, deadline=deadline())
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_request"
        assert {"path": "deadline", "reason": reason} in r.json()["fields"]
        assert poll_count(api) == api.before
        assert api.scheduler.jobs == {}

    def test_send_failure_does_not_schedule(self, api):
        api.guild.channels[500].send_error = http_error(discord.Forbidden, 403)
        r = post(api, deadline=self.future(hours=1).isoformat())
        assert r.status_code == 400
        assert api.scheduler.jobs == {}
        assert poll_count(api) == api.before
