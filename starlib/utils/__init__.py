"""
### 模組：工具集
提供各項函式與方法
"""
from logging import DEBUG, ERROR, INFO, WARNING

from ..fileDatabase import Jsondb
from ..settings import get_settings
from .functions import *
from .logger import create_logger
from .utility import *
from .webUtility import *

settings = get_settings()

file_log = settings.FILE_LOG
debug_mode = settings.DEBUG_MODE
log_level = settings.LOG_LEVEL
#log_level = DEBUG if debug_mode else INFO

log = create_logger("starlib", log_level, file_log=file_log, dir_path="./logs")
apsc_log = create_logger("apscheduler", WARNING, format_str="%(asctime)s [apsc/%(levelname)s] %(message)s")
twitch_log = create_logger("twitchBot", DEBUG, format_str="%(asctime)s [twitchBot/%(levelname)s] %(message)s")
web_log = create_logger("web", log_level, format_str="%(asctime)s [web/%(levelname)s] %(message)s")
agent_log = create_logger("agent", log_level, format_str="%(asctime)s [agent/%(levelname)s] %(message)s")

# discord_log = create_logger("discord", WARNING, format_str="%(asctime)s [%(levelname)s] [discord] %(message)s")
pywarnings = create_logger("py.warnings", ERROR, format_str="%(asctime)s [%(levelname)s] [py.warnings] %(message)s")
