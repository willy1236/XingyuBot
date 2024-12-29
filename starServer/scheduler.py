import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger


def test_job():
    print("Test job executed.")

def run_scheduler():
    scheduler = BackgroundScheduler(timezone="Asia/Taipei")
    
    scheduler.add_job(test_job, CronTrigger(day_of_week=1, hour=9, minute=0))
    
    scheduler.start()
    print("定時任務已啟動。")
    
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        print("定時任務已關閉。")

if __name__ == '__main__':
    run_scheduler()