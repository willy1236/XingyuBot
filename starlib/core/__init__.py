"""
### 模組：核心模組
由StarManager繼承並整合所有內容，使用者可直接調用sclient使用\n
### 各類別功能
各類client: 結合所有資料進行複雜操作\n
StarManager: 繼承所有內容，將基本（直接操作資料庫）及進階（clients）整合
"""
from .client import StarManager

sclient = StarManager()

__all__ = [
    'sclient',
    'StarManager',
]