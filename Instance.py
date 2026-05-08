"""
舊版單例宣告，作為遷移至DI前的過渡方案，此處不應該再新增任何功能，僅保留部分尚未遷移的物件
應逐步棄用此檔案，並將其中的物件遷移至相應的模組中
"""

from v2_starlib.base import get_settings
from v2_starlib.database import create_sqldb
from v2_starlib.fileDatabase import JsonDatabase
from v2_starlib.providers import McssAPI

Jsondb = JsonDatabase()
sqldb = create_sqldb()
happycamp_guild = get_settings().HAPPYCAMP_GUILD
debug_guilds = get_settings().DEBUG_GUILDS

drive_share_guilds = sqldb.get_enable_drive_share_guilds()
mcserver_guilds = sqldb.get_enable_mcserver_guilds()
mcss_api = McssAPI(sqldb)
