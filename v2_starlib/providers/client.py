import tweepy

from .game.platforms import *
from .general.others import *
from .general.weather import *
from .social.platforms import *


class ClientProvider:
    def __init__(self, sqldb: SQLRepository):
        self.sqldb = sqldb
        self.mcss_api = McssAPI(sqldb)
        self.yt_rss = YoutubeRSS()
        self.google_api = GoogleAPI(sqldb)
        self.yt_push = YoutubePush()
        self.tw_api = TwitchAPI(sqldb)
        self.twitter_api = tweepy.Client(sqldb.get_access_token(APIType.Twitter).access_token)
        self.rss_hub = RssHub()
        self.cwa_api = CWA_API(sqldb)
        self.apexapi = ApexAPI(sqldb)
        self.cli_api = CLIInterface(sqldb)
        self.ncdr_rss = NCDRRSS()
