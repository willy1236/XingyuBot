from .funtions import *
from .logger import *
from .utility import *

from starcord.FileDatabase import Jsondb

file_log = Jsondb.jdata.get('file_log')
debug_mode = Jsondb.jdata.get("debug_mode",True)

from logging import INFO,DEBUG
log_level = DEBUG if debug_mode else INFO
log = create_logger('./logs',file_log,log_level)