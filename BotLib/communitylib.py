import requests,datetime,discord
from BotLib.database import Database

class Twitch:
    def __init__(self):
        self.__db = Database()
        self.__headers = self.__get_twitch_token()

    def __get_twitch_token(self):
        APIURL = "https://id.twitch.tv/oauth2/token"
        #headers = {"Content-Type": "application/x-www-form-urlencoded"}
        tokens = self.__db.get_token('twitch')
        params = {
            'client_id':tokens[0],
            'client_secret':tokens[1],
            'grant_type':'client_credentials'
            }

        r = requests.post(APIURL, params=params).json()
        headers = {
            'Authorization': f"Bearer {r['access_token']}",
            'Client-Id':tokens[0]
        }
        return headers

    def get_live(self,users:list):
        """取得twitch用戶的直播資訊（若無直播則為空）\n
        字典內格式 -> username: embed | None
        """
        URL = 'https://api.twitch.tv/helix/streams'
        params = {
            "user_login": users,
            "first": 1
        }
        r = requests.get(URL, params=params,headers=self.__headers).json()
        dict = {}
        for user in users:
            dict[user] = None

        for data in r['data']:
            user = data['user_login']
            time = datetime.datetime.strptime(data['started_at'],'%Y-%m-%dT%H:%M:%SZ')+datetime.timedelta(hours=8)
            time = time.strftime('%Y/%m/%d %H:%M:%S')
            
            embed = discord.Embed(
                title=data['title'],
                url=f"https://www.twitch.tv/{data['user_login']}",
                description=f"{data['game_name']}",
                color=0x6441a5,
                timestamp = datetime.datetime.now()
                )
            embed.set_author(name=f"{data['user_name']} 開台啦！")
            thumbnail = data['thumbnail_url']
            thumbnail = thumbnail.replace('{width}','960')
            thumbnail = thumbnail.replace('{height}','540')
            embed.set_image(url=thumbnail)
            embed.set_footer(text=f"開始於{time}")
            dict[user] = embed
        
        return dict

class Twitter:
    pass