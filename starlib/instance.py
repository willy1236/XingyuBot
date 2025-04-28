"""
此處提供bot在初始化與執行時所需的設定與物件（如api等）
"""
import tweepy

from .dataExtractor import *
from .dataExtractor.others import McssAPI
from .fileDatabase import Jsondb

__all__ = [
    "mcss_api",
    "yt_rss",
    "yt_api",
    "yt_push",
    "tw_api",
    "rss_hub",
    "cwa_api",
    "apexapi",
    "main_guilds",
    "happycamp_guild",
    "debug_guilds",
    "debug_mode",
]

# api
mcss_api = McssAPI()
yt_rss = YoutubeRSS()
yt_api = YoutubeAPI()
yt_push = YoutubePush()
tw_api = TwitchAPI()
twitter_api = tweepy.Client(Jsondb.get_token("x_api"))
rss_hub = RssHub()
cwa_api = CWA_API()
apexapi = ApexAPI()

# jsondb
main_guilds: list[int] = Jsondb.config.get('main_guilds', [])
happycamp_guild: list[int] = Jsondb.config.get('happycamp_guild', [])
debug_guilds: list[int] = Jsondb.config.get('debug_guilds', [])
debug_mode: bool = Jsondb.config.get("debug_mode", True)