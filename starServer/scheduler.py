import asyncio
import threading
import time

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from starlib import log, tz


def test_job():
    print("Test job executed.")


def run_scheduler():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    scheduler = AsyncIOScheduler(timezone=tz, event_loop=loop)

    # scheduler.add_job(test_job, CronTrigger(day_of_week=1, hour=9, minute=0))
    # scheduler.add_job(test_job, IntervalTrigger(seconds=5))

    scheduler.start()
    log.info("Scheduler started.")
    loop.run_forever()


def run_scheduler_in_thread():
    scheduler_thread = threading.Thread(target=run_scheduler, name="AsyncScheduler", daemon=True)
    scheduler_thread.start()


if __name__ == "__main__":
    run_scheduler_in_thread()
    while True:
        time.sleep(10)
