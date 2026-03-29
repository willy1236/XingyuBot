"""
### 模組：工具集
提供各項函式與方法
"""
from logging import DEBUG, ERROR, INFO, WARNING

from ..fileDatabase import Jsondb
from .functions import *
from .logger import create_logger
from .utility import *
from .webUtility import *

file_log = Jsondb.config.get("file_log")
debug_mode = Jsondb.config.get("debug_mode",True)
log_level = Jsondb.config.get("log_level",INFO)
#log_level = DEBUG if debug_mode else INFO

log = create_logger("starlib", log_level, file_log=True, dir_path="./logs")
apsc_log = create_logger("apscheduler", WARNING, format_str="%(asctime)s [apsc/%(levelname)s] %(message)s")
twitch_log = create_logger("twitchBot", DEBUG, format_str="%(asctime)s [twitchBot/%(levelname)s] %(message)s")
web_log = create_logger("web", log_level, format_str="%(asctime)s [web/%(levelname)s] %(message)s")
agent_log = create_logger("agent", log_level, format_str="%(asctime)s [agent/%(levelname)s] %(message)s")

# discord_log = create_logger("discord", WARNING, format_str="%(asctime)s [%(levelname)s] [discord] %(message)s")
pywarnings = create_logger("py.warnings", ERROR, format_str="%(asctime)s [%(levelname)s] [py.warnings] %(message)s")
