"""
### 模組：資料處理器
蒐集各來源資料並加以處理，同時提供操作以修改資料\n
### 各類別功能
"""

from .community import *
from .game import *
from .oauth import *
from .weather import *

__all__ =[
    'TwitchAPI',
    'YoutubeAPI',
    'GoogleCloud',
    'NotionAPI',
    'RiotAPI',
    'OsuAPI',
    'ApexAPI',
    'SteamAPI',
    'DBDInterface',
    'LOLMediaWikiAPI',
    'CWA_API',
    'YoutubeRSS',
    "DiscordOauth2",
    'YoutubePush',
]