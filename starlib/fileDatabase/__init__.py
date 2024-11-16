'''
### 模組：本地資料庫
負責本地資料之操作與管理
'''

from .csv import CsvDatabase
from .json import JsonDatabase

Jsondb = JsonDatabase()
csvdb = CsvDatabase()

main_guilds = Jsondb.config.get('main_guilds',[])
happycamp_guild = Jsondb.config.get('happycamp_guild',[])
debug_guilds = Jsondb.config.get('debug_guilds',[])

__all__ = [
    'JsonDatabase',
    'Jsondb',
    'CsvDatabase',
    'csvdb',
]
