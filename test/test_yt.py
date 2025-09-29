from starlib import YoutubeAPI, YoutubePush, sqldb, APIType

api = YoutubeAPI()

callback_url = sqldb.get_bot_token(APIType.Google, 4).callback_uri
print(YoutubePush().get_push("", callback_url))
