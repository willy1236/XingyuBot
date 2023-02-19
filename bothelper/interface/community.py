import requests,datetime
from bothelper.database import JsonDatabase
from bothelper.model.community import *

class CommunityInterface():
    def __init__(self):
        self.db = JsonDatabase()

class Twitch(CommunityInterface):
    '''
    與Twitch api交互相關
    '''
    def __init__(self):
        super().__init__()
        self.__headers = self.__get_headers()

    def __get_headers(self):
        APIURL = "https://id.twitch.tv/oauth2/token"
        #headers = {"Content-Type": "application/x-www-form-urlencoded"}
        tokens = self.db.get_token('twitch')
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

    def get_lives(self,users:list):
        """
        取得twitch用戶的直播資訊
        
        Args:
            users: list of users

        Returns:
            dict: {username: TwitchStream | None（如果無正在直播）}
        """
        URL = 'https://api.twitch.tv/helix/streams'
        params = {
            "user_login": users,
            "first": 1
        }
        r = requests.get(URL, params=params,headers=self.__headers)
        apidata = r.json()
        dict = {}
        for user in users:
            dict[user] = None

        for data in apidata['data']:
            dict[data.get('user_login')] = TwitchStream(data)
        
        return dict

    def get_user(self,username:str):
        """
        取得Twitch用戶
        
        Args:
            username: 用戶名稱（user_login）
        """
        URL = 'https://api.twitch.tv/helix/users'
        params = {
            "login": username,
            "first": 1
        }
        r = requests.get(URL, params=params,headers=self.__headers)
        apidata = r.json()
        if apidata.get('data'):
            return TwitchUser(apidata['data'][0])
        else:
            return None

class TwitterInterface:
    pass

class YoutubeInterface(CommunityInterface):
    def __init__(self):
        super().__init__()
        self.__token = self.db.get_token('youtube')
        self.__headers = {
            'Authorization': f'Bearer {self.__token}',
            'Accept': 'application/json'
        }

    def get_channel_id(self,channel_name:str):
        params = {
            'key': self.__token,
            'forUsername': channel_name,
            'part': 'id',
            'maxResults':1
        }
        r = requests.get('https://youtube.googleapis.com/youtube/v3/channels',params=params)
        if r.status_code == 200:
            print(r)
            print(r.json())
        else:
            print(r.text)
            print(r.status_code)

    def get_channel_content(self,channel_name:str):
        params = {
            'key': self.__token,
            'forUsername': channel_name,
            'part': 'contentDetails,snippet',
            'maxResults':1
        }
        r = requests.get('https://youtube.googleapis.com/youtube/v3/channels',params=params)
        if r.status_code == 200:
            print(r)
            print(r.json())
        else:
            print(r.text)
            print(r.status_code)

    def get_channelsection(self,channel_id:str):
        params = {
            'key': self.__token,
            'channelId': channel_id,
            'part': 'contentDetails'
        }
        r = requests.get('https://www.googleapis.com/youtube/v3/channelSections',params=params)
        if r.status_code == 200:
            print(r)
            print(r.json())
        else:
            print(r.text)
            print(r.status_code)

    def get_streams(self,channel_ids:list):
        print(','.join(channel_ids))
        params ={
            'key': self.__token,
            'part': 'snippet',
            'channelId': ','.join(channel_ids),
            'eventType':'live',
            'type': 'video'
        }
        r = requests.get('https://www.googleapis.com/youtube/v3/search',params=params)
        if r.status_code == 200:
            print(r)
            print(r.json())
        else:
            print(r.text)
            print(r.status_code)