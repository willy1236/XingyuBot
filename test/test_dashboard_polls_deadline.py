"""投票截止時間 V-04：排程、自動結算、訊息顯示（假 Discord 與假 scheduler，真實 PostgreSQL）。"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from apscheduler.jobstores.base import JobLookupError
from test_dashboard_polls_core import (  # noqa: F401
    CHANNEL_ID,
    GUILD_ID,
    FakeBot,
    FakeChannel,
    FakeMessage,
    add_poll,
    fake_chart,
    stored,
)
from test_identity import repo  # noqa: F401

from starDiscord.uiElement.view import PollView
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
