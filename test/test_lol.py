import datetime as dt

from starlib.dataExtractor.game import LOLMediaWikiAPI
print(LOLMediaWikiAPI().get_date_games(dt.date(2025, 2, 23)))