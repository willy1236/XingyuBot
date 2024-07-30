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

log = create_logger('./logs', file_log, log_level)
apsc_log = create_logger('./logs', False, WARNING, "apscheduler", format="%(asctime)s [apsc/%(levelname)s] %(message)s")

twitch_log = create_logger('./logs', False, DEBUG, "twitch_log", format="%(asctime)s [twitch_bot/%(levelname)s] %(message)s")

# discord_log = create_logger('./logs', False, DEBUG, "discord", format="%(asctime)s [%(levelname)s] [discord] %(message)s")