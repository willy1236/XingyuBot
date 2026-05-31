"""
### 模組：資料庫
處理資料庫連線與操作。
"""
from .postgresql.client import create_sqldb
from .postgresql.enums import *
from .postgresql.models import *

sqldb = create_sqldb()
__all__ = [
    "sqldb",
]
