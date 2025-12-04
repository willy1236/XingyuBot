"""
此處提供bot在初始化與執行時所需的設定與物件（如api等）
"""
import tweepy

from .database import sqldb
from .dataExtractor import *
from .dataExtractor.others import McssAPI
from .fileDatabase import Jsondb
from .types import APIType

__all__ = [
    "mcss_api",
    "yt_rss",
    "google_api",
    "yt_push",
    "tw_api",
    "rss_hub",
    "cwa_api",
    "apexapi",
    "cli_api",
    "ncdr_rss",
    "main_guilds",
    "happycamp_guild",
    "debug_guilds",
    "debug_mode",
]

# api
mcss_api = McssAPI()
yt_rss = YoutubeRSS()
google_api = GoogleAPI()
yt_push = YoutubePush()
tw_api = TwitchAPI()
twitter_api = tweepy.Client(sqldb.get_access_token(APIType.Twitter).access_token)
rss_hub = RssHub()
cwa_api = CWA_API()
apexapi = ApexAPI()
cli_api = CLIInterface()
ncdr_rss = NCDRRSS()

# jsondb
main_guilds: list[int] = Jsondb.config.get("main_guilds", [])
happycamp_guild: list[int] = Jsondb.config.get("happycamp_guild", [])
debug_guilds: list[int] = Jsondb.config.get("debug_guilds", [])
debug_mode: bool = Jsondb.config.get("debug_mode", True)
