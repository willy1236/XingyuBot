"""
此處提供bot在初始化與執行時所需的設定與物件（如api等）
"""

import tweepy

from .database import APIType, sqldb
from .fileDatabase import Jsondb
from .providers import *
from .settings import get_settings

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
    "drive_share_guilds",
    "mcserver_guilds",
    "happycamp_guild",
    "debug_guilds",
    "debug_mode",
    "task_report",
    "feedback_channel",
    "error_report",
    "report_channel",
    "dm_channel",
    "mentioned_channel",
    "mention_everyone_channel",
    "vip_admin_channel",
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

settings = get_settings()

# runtime settings
drive_share_guilds: list[int] = sqldb.get_enable_drive_share_guilds()
mcserver_guilds: list[int] = sqldb.get_enable_mcserver_guilds()
happycamp_guild: list[int] = settings.HAPPYCAMP_GUILD
debug_guilds: list[int] = settings.DEBUG_GUILDS
debug_mode: bool = settings.DEBUG_MODE
task_report: int = settings.TASK_REPORT
feedback_channel: int = settings.FEEDBACK_CHANNEL
error_report: int = settings.ERROR_REPORT
report_channel: int = settings.REPORT_CHANNEL
dm_channel: int = settings.DM_CHANNEL
mentioned_channel: int = settings.MENTIONED_CHANNEL
mention_everyone_channel: int = settings.MENTION_EVERYONE_CHANNEL
vip_admin_channel: int = settings.VIP_ADMIN_CHANNEL
