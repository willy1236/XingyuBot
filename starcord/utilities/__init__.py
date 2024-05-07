"""
### 模組：工具集
提供各項函式與方法
"""
from starcord.FileDatabase import Jsondb

from .funtions import *
from .logger import *
from .utility import *
from .task import scheduler

file_log = Jsondb.jdata.get('file_log')
debug_mode = Jsondb.jdata.get("debug_mode",True)

from logging import INFO,DEBUG
#log_level = DEBUG if debug_mode else INFO
log = create_logger('./logs',file_log)

twitch_log = create_logger('./logs',False,INFO,"twitch_log",format="%(asctime)s [%(levelname)s] [twitch_bot] %(message)s")