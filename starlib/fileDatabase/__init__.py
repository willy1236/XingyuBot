"""
### 模組：本地資料庫
負責本地資料之操作與管理
"""

from .csv import CsvDatabase
from .json import JsonDatabase

Jsondb = JsonDatabase()
csvdb = CsvDatabase()

__all__ = [
    "JsonDatabase",
    "Jsondb",
    "CsvDatabase",
    "csvdb",
]
