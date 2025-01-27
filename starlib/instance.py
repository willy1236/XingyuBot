"""
此處提供bot在初始化與執行時所需的設定與物件（如api等）
"""

from .dataExtractor import *
from .dataExtractor.others import McssAPI
from .fileDatabase import Jsondb

__all__ = [
    "mcss_api",
    "yt_rss",
    "yt_api",
    "yt_push",
    "tw_api",
    "cwa_api",
    "apexapi",
    "main_guilds",
    "happycamp_guild",
    "debug_guilds"
]

# api
mcss_api = McssAPI()
yt_rss = YoutubeRSS()
yt_api = YoutubeAPI()
yt_push = YoutubePush()
tw_api = TwitchAPI()
cwa_api = CWA_API()
apexapi = ApexAPI()

# jsondb
main_guilds = Jsondb.config.get('main_guilds',[])
happycamp_guild = Jsondb.config.get('happycamp_guild',[])
debug_guilds = Jsondb.config.get('debug_guilds',[])