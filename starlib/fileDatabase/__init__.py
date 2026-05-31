"""
### 模組：本地資料庫
負責本地資料之操作與管理
"""


from .json import JsonDatabase

Jsondb = JsonDatabase()

__all__ = [
    "JsonDatabase",
    "Jsondb",
]
