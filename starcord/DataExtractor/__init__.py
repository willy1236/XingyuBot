"""
### 模組：資料處理器
蒐集各來源資料並加以處理，同時提供操作以修改資料\n
由StarManager繼承並整合所有內容，使用者可直接調用sclient使用\n
### 各類別功能
"""

from .community import *
from .game import *
from .weather import *
from .oauth import *

__all__ =[
    'TwitchAPI',
    'YoutubeAPI',
    'GoogleCloud',
    'NotionAPI',
    'RiotAPI',
    'OsuInterface',
    'ApexInterface',
    'SteamInterface',
    'DBDInterface',
    'CWA_API',
    'YoutubeRSS',
]