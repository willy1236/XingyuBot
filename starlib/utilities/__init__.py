"""
### 模組：工具集
提供各項函式與方法
"""
from logging import INFO, DEBUG, WARNING

from ..fileDatabase import Jsondb
from .funtions import *
from .logger import *
from .utility import *
from .task import scheduler

file_log = Jsondb.config.get('file_log')
debug_mode = Jsondb.config.get("debug_mode",True)
log_level = Jsondb.config.get("log_level",INFO)
#log_level = DEBUG if debug_mode else INFO

log = create_logger(log_level=log_level, file_log=file_log)
apsc_log = create_logger("apscheduler", WARNING, format="%(asctime)s [apsc/%(levelname)s] %(message)s")
twitch_log = create_logger("twitch_log", DEBUG, format="%(asctime)s [twitch_bot/%(levelname)s] %(message)s")
web_log = create_logger("web_log", INFO, format="%(asctime)s [web/%(levelname)s] %(message)s")

# discord_log = create_logger('./logs', False, DEBUG, "discord", format="%(asctime)s [%(levelname)s] [discord] %(message)s")