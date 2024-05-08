import logging

#from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# TODO: move to ./logger.py
apsc_log = logging.getLogger('apscheduler')
formatter = logging.Formatter('%(asctime)s [%(levelname)s] [apsc] %(message)s')
consoleHandler = logging.StreamHandler()
consoleHandler.setLevel(logging.INFO)
consoleHandler.setFormatter(formatter)
apsc_log.addHandler(consoleHandler)

scheduler = AsyncIOScheduler()
# scheduler.start()