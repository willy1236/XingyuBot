"""
### 模組：providers
此模組作為 starlib 函式庫的「資料供應層 (Data Provider Layer)」。
主要負責與外部第三方服務、API 接口或異質資料源進行通訊與資料抓取。
"""

from .game.platforms import *
from .general.others import *
from .general.weather import *
from .social.platforms import *

__all__ = [
    "TwitchAPI",
    "GoogleAPI",
    "XingyuGoogleCloud",
    "NotionAPI",
    "RiotAPI",
    "OsuAPI",
    "ApexAPI",
    "SteamAPI",
    "DBDInterface",
    "LOLMediaWikiAPI",
    "ZeroTierAPI",
    "CWA_API",
    "NCDRRSS",
    "YoutubeRSS",
    "YoutubePush",
    "RssHub",
    "CLIInterface",
    "McssAPI",
]
