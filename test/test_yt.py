from starlib import GoogleAPI, YoutubePush, sqldb, APIType

api = GoogleAPI()

callback_url = sqldb.get_bot_token(APIType.Google, 4).callback_uri
records = sqldb.get_expiring_push_records()
for record in records:
    print(YoutubePush().add_push(record.channel_id, callback_url))
