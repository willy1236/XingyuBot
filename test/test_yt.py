from starlib import GoogleAPI, YoutubePush, sqldb, APIType

api = GoogleAPI()

callback_url = sqldb.get_bot_token(APIType.Google, 4).callback_uri
print(YoutubePush().get_push("", callback_url))
