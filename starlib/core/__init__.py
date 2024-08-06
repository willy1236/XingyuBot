"""
### 模組：核心模組
由StarManager繼承並整合所有內容，使用者可直接調用sclient使用\n
### 各類別功能
各類client: 結合所有資料進行複雜操作\n
StarManager：提供各資料間的資料交換\n
"""
from .client import StarManager

sclient = StarManager()

__all__ = [
    'sclient',
    'StarManager',
]