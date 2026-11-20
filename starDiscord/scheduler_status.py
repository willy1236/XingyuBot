"""Discord bot 排程任務的最近一次執行結果，給營運入口的系統分頁看。

APScheduler 不保存執行結果，這裡掛 listener 記在記憶體，重啟後歸零（任務卡 O-04 待決 1）。
只記週期任務：`DateTrigger` 的一次性 job（抽獎、投票結束、開台通知）不記也不列。
listener 與 `snapshot()` 都在 scheduler 的 event loop（bot 的主 loop）上執行，狀態不加鎖。
"""

import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from apscheduler.events import (
    EVENT_JOB_ERROR,
    EVENT_JOB_EXECUTED,
    EVENT_JOB_MAX_INSTANCES,
    EVENT_JOB_MISSED,
    EVENT_JOB_SUBMITTED,
    JobEvent,
    JobExecutionEvent,
    JobSubmissionEvent,
)
from apscheduler.job import Job
from apscheduler.schedulers.base import BaseScheduler
from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.cron.expressions import AllExpression, RangeExpression
from apscheduler.triggers.cron.fields import BaseField
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from starlib.utils import nowtz

type RunResult = Literal["success", "error", "missed", "skipped"]

# 錯誤訊息（含 traceback）的長度上限
ERROR_MAX = 4000
# 超過上限時，類型與訊息最多保留的長度；其餘留給 traceback 的尾段
ERROR_HEAD_MAX = 1000
ERROR_CUT = "\n…（中間省略）…\n"


@dataclass(frozen=True, slots=True)
class LastRun:
    at: datetime
    result: RunResult
    # 只有 success、error 有耗時
    duration_ms: int | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class JobStatus:
    id: str
    name: str
    trigger: str
    # 暫停中的任務為 None
    next_run_at: datetime | None
    # 啟動後還沒執行過為 None
    last: LastRun | None

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["next_run_at"] = None if self.next_run_at is None else self.next_run_at.isoformat()
        if self.last is not None:
            data["last"]["at"] = self.last.at.isoformat()
        return data


_scheduler: BaseScheduler | None = None
_last: dict[str, LastRun] = {}
# job id -> (送出時間, monotonic)，執行完時算耗時
_submitted: dict[str, tuple[datetime, float]] = {}


def install(scheduler: BaseScheduler) -> None:
    """在 scheduler 上掛 listener 記錄每個週期任務最近一次的結果；之後 `snapshot()` 讀這個 scheduler。"""
    global _scheduler
    _scheduler = scheduler
    _last.clear()
    _submitted.clear()
    scheduler.add_listener(
        _on_event,
        EVENT_JOB_SUBMITTED | EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED | EVENT_JOB_MAX_INSTANCES,
    )


def _periodic(job: Job | None) -> bool:
    return job is not None and not isinstance(job.trigger, DateTrigger)


def _on_event(event: JobEvent) -> None:
    assert _scheduler is not None
    # 一次性 job 跑完就從 scheduler 移除，這時 get_job 是 None，同樣不記
    if not _periodic(_scheduler.get_job(event.job_id)):
        _submitted.pop(event.job_id, None)
        return
    if event.code == EVENT_JOB_SUBMITTED:
        _submitted[event.job_id] = (nowtz(), time.monotonic())
    elif event.code == EVENT_JOB_MAX_INSTANCES:
        assert isinstance(event, JobSubmissionEvent)
        _last[event.job_id] = LastRun(at=event.scheduled_run_times[-1], result="skipped")
    elif event.code == EVENT_JOB_MISSED:
        assert isinstance(event, JobExecutionEvent)
        _last[event.job_id] = LastRun(at=event.scheduled_run_time, result="missed")
    else:
        assert isinstance(event, JobExecutionEvent)
        started_at, started = _submitted.pop(event.job_id, (event.scheduled_run_time, None))
        duration_ms = None if started is None else round((time.monotonic() - started) * 1000)
        if event.code == EVENT_JOB_ERROR:
            _last[event.job_id] = LastRun(
                at=started_at,
                result="error",
                duration_ms=duration_ms,
                error=error_text(event.exception, event.traceback),
            )
        else:
            _last[event.job_id] = LastRun(at=started_at, result="success", duration_ms=duration_ms)


def error_text(exception: BaseException | None, traceback: str | None) -> str:
    """「類型: 訊息」加 traceback，總長不超過 ERROR_MAX。

    超過時保留開頭的類型與訊息（最多 ERROR_HEAD_MAX 字）與 traceback 的尾段：最接近出錯點的 frame 在最後。
    """
    head = f"{type(exception).__name__}: {exception}"
    tb = (traceback or "").rstrip()
    full = f"{head}\n{tb}" if tb else head
    if len(full) <= ERROR_MAX:
        return full
    head = head[:ERROR_HEAD_MAX]
    room = ERROR_MAX - len(head) - len(ERROR_CUT)
    return f"{head}{ERROR_CUT}{tb[-room:]}"


def snapshot() -> list[JobStatus]:
    """所有週期任務的下次執行時間與最近一次結果。最近一次不是成功的排最前面，其餘依下次執行時間。

    要在 scheduler 的 event loop 上呼叫；還沒 `install` 時回空清單。
    """
    if _scheduler is None:
        return []
    jobs = [
        JobStatus(
            id=job.id,
            name=job.name,
            trigger=describe_trigger(job.trigger),
            next_run_at=job.next_run_time,
            last=_last.get(job.id),
        )
        for job in _scheduler.get_jobs()
        if _periodic(job)
    ]
    far = nowtz() + timedelta(days=36500)
    jobs.sort(key=lambda j: (j.last is None or j.last.result == "success", j.next_run_at or far))
    return jobs


# ── trigger 轉成可讀文字 ──────────────────────────────────

# 欄位的簡化形式：("any",)、("fixed", n)、("step", 起點, 間隔)、("list", [n, ...])；其他寫法為 None
type _Simple = tuple[Any, ...] | None


def _simple(field: BaseField) -> _Simple:
    exprs = field.expressions
    if len(exprs) == 1:
        e = exprs[0]
        if type(e) is AllExpression:
            return ("any",) if e.step in (None, 1) else ("step", 0, e.step)
        if type(e) is RangeExpression:
            if e.step is None and e.last == e.first:
                return ("fixed", e.first)
            if e.step is not None and e.last is None:
                return ("any",) if e.step == 1 and e.first == 0 else ("step", e.first, e.step)
        return None
    if all(type(e) is RangeExpression and e.step is None and e.last == e.first for e in exprs):
        return ("list", [e.first for e in exprs])
    return None


def _clock(hour: int, minute: int, second: int) -> str:
    return f"{hour:02d}:{minute:02d}" + (f":{second:02d}" if second else "")


def _describe_cron(trigger: CronTrigger) -> str | None:
    f = {field.name: _simple(field) for field in trigger.fields}
    if any(v is None for v in f.values()) or f["year"] != ("any",) or f["week"] != ("any",):
        return None
    month, day, dow = f["month"], f["day"], f["day_of_week"]
    hour, minute, second = f["hour"], f["minute"], f["second"]
    if second is None or second[0] != "fixed":
        return None
    sec = second[1]

    # 日期部分：每天、每月 D 日、每年 M 月 D 日
    if month == ("any",) and day == ("any",) and dow == ("any",):
        date = "每天"
    elif month == ("any",) and day[0] == "fixed" and dow == ("any",):
        date = f"每月 {day[1]} 日"
    elif month[0] == "fixed" and day[0] == "fixed" and dow == ("any",):
        date = f"每年 {month[1]} 月 {day[1]} 日"
    else:
        return None

    if hour[0] == "fixed" and minute[0] == "fixed":
        return f"{date} {_clock(hour[1], minute[1], sec)}"
    if date != "每天":
        return None
    if hour[0] == "list" and minute[0] == "fixed":
        return "每天 " + "、".join(_clock(h, minute[1], sec) for h in hour[1])
    if hour[0] == "step" and minute[0] == "fixed":
        if hour[1] == 0 and minute[1] == 0 and not sec:
            return f"每 {hour[2]} 小時"
        return f"每 {hour[2]} 小時（{_clock(hour[1], minute[1], sec)} 起）"
    if hour != ("any",):
        return None
    sec_text = f" {sec} 秒" if sec else ""
    if minute == ("any",):
        return f"每分鐘第 {sec} 秒" if sec else "每分鐘"
    if minute[0] == "fixed":
        return f"每小時 {minute[1]:02d} 分{sec_text}"
    if minute[0] == "list":
        return "每小時 " + "、".join(f"{m:02d}" for m in minute[1]) + f" 分{sec_text}"
    start, step = minute[1], minute[2]
    if start == 0 and not sec:
        return f"每 {step} 分鐘"
    return f"每 {step} 分鐘（{start:02d} 分 {sec:02d} 秒起）"


def _describe_interval(interval: timedelta) -> str:
    seconds = int(interval.total_seconds())
    for unit, size in (("天", 86400), ("小時", 3600), ("分鐘", 60)):
        if seconds % size == 0:
            n = seconds // size
            return f"每{unit}" if n == 1 else f"每 {n} {unit}"
    return f"每 {seconds} 秒"


def describe_trigger(trigger: BaseTrigger) -> str:
    """把 cron、interval trigger 轉成「每 3 分鐘」「每天 00:00」這類文字；認不得的寫法回傳 APScheduler 的原始表示。"""
    if isinstance(trigger, IntervalTrigger):
        return _describe_interval(trigger.interval)
    if isinstance(trigger, CronTrigger):
        text = _describe_cron(trigger)
        if text is not None:
            return text
    return str(trigger)
