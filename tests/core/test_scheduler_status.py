"""starDiscord.scheduler_status：週期排程任務最近一次的結果與 trigger 的可讀文字（真的 AsyncIOScheduler，不碰 DB）。"""

import asyncio
from datetime import timedelta

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from starDiscord import scheduler_status
from starlib.utils import nowtz


async def ok():
    return None


async def boom():
    raise ValueError("壞掉了")


async def slow():
    await asyncio.sleep(0.6)


def run_scheduler(setup, seconds: float):
    """在新的 loop 上建立 scheduler、install、加 job、跑 seconds 秒後回傳 snapshot。"""

    async def scenario():
        scheduler = AsyncIOScheduler()
        scheduler_status.install(scheduler)
        setup(scheduler)
        scheduler.start()
        await asyncio.sleep(seconds)
        try:
            return scheduler_status.snapshot()
        finally:
            scheduler.shutdown(wait=False)

    return asyncio.run(scenario())


def by_id(jobs):
    return {job.id: job for job in jobs}


def test_results_of_success_error_missed_and_not_yet_run():
    def setup(s):
        now = nowtz()
        s.add_job(ok, "interval", hours=1, id="ok", name="成功", next_run_time=now)
        s.add_job(boom, "interval", hours=1, id="boom", name="失敗", next_run_time=now)
        s.add_job(
            ok,
            "interval",
            hours=1,
            id="late",
            name="錯過",
            next_run_time=now - timedelta(seconds=30),
            misfire_grace_time=1,
        )
        s.add_job(ok, "interval", hours=1, id="idle", name="還沒跑")

    jobs = by_id(run_scheduler(setup, 0.3))

    assert jobs["ok"].last.result == "success"
    assert jobs["ok"].last.duration_ms is not None
    assert jobs["boom"].last.result == "error"
    assert jobs["boom"].last.error.startswith("ValueError: 壞掉了")
    assert "raise ValueError" in jobs["boom"].last.error
    assert jobs["late"].last.result == "missed"
    assert jobs["late"].last.duration_ms is None
    assert jobs["idle"].last is None
    assert jobs["idle"].name == "還沒跑"
    assert jobs["idle"].trigger == "每小時"
    assert jobs["idle"].next_run_at is not None


def test_run_skipped_while_previous_still_running():
    def setup(s):
        s.add_job(slow, IntervalTrigger(seconds=0.2), id="slow", max_instances=1, next_run_time=nowtz())

    jobs = by_id(run_scheduler(setup, 0.5))
    assert jobs["slow"].last.result == "skipped"


def test_one_off_jobs_are_not_listed_or_recorded():
    def setup(s):
        s.add_job(ok, DateTrigger(nowtz()), id="poll_end_1")
        s.add_job(ok, DateTrigger(nowtz() + timedelta(hours=1)), id="poll_end_2")
        s.add_job(ok, "interval", hours=1, id="periodic")

    assert [job.id for job in run_scheduler(setup, 0.3)] == ["periodic"]
    assert "poll_end_1" not in scheduler_status._last


def test_problems_come_first_then_by_next_run():
    def setup(s):
        now = nowtz()
        s.add_job(ok, "interval", hours=3, id="later")
        s.add_job(ok, "interval", hours=1, id="sooner")
        s.add_job(boom, "interval", hours=5, id="broken", next_run_time=now)
        s.add_job(ok, "interval", hours=2, id="fine", next_run_time=now)

    assert [job.id for job in run_scheduler(setup, 0.3)] == ["broken", "sooner", "fine", "later"]


def test_json_shape():
    def setup(s):
        s.add_job(boom, "interval", minutes=3, id="boom", name="地震報告", next_run_time=nowtz())

    data = run_scheduler(setup, 0.3)[0].to_json()
    assert set(data) == {"id", "name", "trigger", "next_run_at", "last"}
    assert data["trigger"] == "每 3 分鐘"
    assert isinstance(data["next_run_at"], str)
    assert set(data["last"]) == {"at", "result", "duration_ms", "error"}
    assert isinstance(data["last"]["at"], str)


def test_snapshot_before_install_is_empty(monkeypatch):
    monkeypatch.setattr(scheduler_status, "_scheduler", None)
    assert scheduler_status.snapshot() == []


# starDiscord/cmds/task.py 實際用到的寫法
@pytest.mark.parametrize(
    ("kwargs", "text"),
    [
        ({"hour": "0/3", "minute": 0, "second": 1}, "每 3 小時（00:00:01 起）"),
        ({"minute": "20,35", "second": 30}, "每小時 20、35 分 30 秒"),
        ({"minute": "0/15", "second": 10}, "每 15 分鐘（00 分 10 秒起）"),
        ({"hour": "2/12", "minute": 0, "second": 0, "jitter": 300}, "每 12 小時（02:00 起）"),
        ({"minute": "0/20", "second": 0}, "每 20 分鐘"),
        ({"hour": "0/1", "minute": "0/30", "second": 0}, "每 30 分鐘"),
        ({"hour": "0/2", "minute": 0, "second": 0}, "每 2 小時"),
        ({"minute": 5, "second": 0}, "每小時 05 分"),
        ({"minute": "*/1", "second": 30}, "每分鐘第 30 秒"),
        ({"month": 10, "day": 16, "hour": 8, "minute": 0, "second": 0}, "每年 10 月 16 日 08:00"),
        ({"hour": 0, "minute": 0, "second": 0}, "每天 00:00"),
    ],
)
def test_describe_cron(kwargs, text):
    assert scheduler_status.describe_trigger(CronTrigger(**kwargs)) == text


@pytest.mark.parametrize(
    ("kwargs", "text"),
    [
        ({"minutes": 3}, "每 3 分鐘"),
        ({"minutes": 1}, "每分鐘"),
        ({"hours": 2}, "每 2 小時"),
        ({"seconds": 90}, "每 90 秒"),
    ],
)
def test_describe_interval(kwargs, text):
    assert scheduler_status.describe_trigger(IntervalTrigger(**kwargs)) == text


def test_unrecognized_cron_falls_back_to_raw():
    trigger = CronTrigger(day_of_week="mon", hour=1)
    assert scheduler_status.describe_trigger(trigger) == str(trigger)


def test_short_error_keeps_everything():
    assert scheduler_status.error_text(ValueError("壞掉了"), "  File a\n") == "ValueError: 壞掉了\n  File a"


def test_long_error_keeps_message_and_traceback_tail():
    tb = "".join(f'  File "frame{i}.py", line {i}\n' for i in range(500)) + '  File "innermost.py", line 1\n'
    text = scheduler_status.error_text(ValueError("壞掉了"), tb)
    assert len(text) <= scheduler_status.ERROR_MAX
    assert text.startswith("ValueError: 壞掉了")
    assert text.endswith('File "innermost.py", line 1')
    assert "frame0.py" not in text
    assert "中間省略" in text


def test_huge_message_is_capped_so_traceback_tail_still_fits():
    text = scheduler_status.error_text(ValueError("x" * 10000), '  File "innermost.py", line 1\n')
    assert len(text) <= scheduler_status.ERROR_MAX
    assert text.endswith('File "innermost.py", line 1')
