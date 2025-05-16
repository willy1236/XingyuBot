from starlib.dataExtractor.oauth import TwitchOauth2
from starlib import sqldb
from starlib.types import APIType


token = sqldb.get_bot_token(APIType.Twitch)
auth = TwitchOauth2.from_bot_token(token)
print(type(auth))
print(auth.user_id)
