import requests
from starcord.database import Jsondb
from starcord.model.community import *

class CommunityInterface():
    """社群資料交互"""

class TwitchAPI(CommunityInterface):
    '''
    與Twitch api交互相關
    '''
    def __init__(self):
        self.__headers = self.__get_headers()
        self.url = "https://api.twitch.tv/helix"

    def __get_headers(self):
        #客戶端憑據僅能使用API
        TOKENURL = "https://id.twitch.tv/oauth2/token"
        #headers = {"Content-Type": "application/x-www-form-urlencoded"}
        tokens = Jsondb.get_token('twitch')
        params = {
            'client_id':tokens[0],
            'client_secret':tokens[1],
            'grant_type':'client_credentials'
            }

        r = requests.post(TOKENURL, params=params).json()
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
        params = {
            "user_login": users,
            "first": 1
        }
        r = requests.get(f"{self.url}/streams", params=params,headers=self.__headers)
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
        params = {
            "login": username,
            "first": 1
        }
        r = requests.get(f"{self.url}/users", params=params,headers=self.__headers)
        apidata = r.json()
        if apidata.get('data'):
            return TwitchUser(apidata['data'][0])
        else:
            return None

class TwitterInterface:
    pass

class YoutubeAPI(CommunityInterface):
    def __init__(self):
        self.__token = Jsondb.get_token('youtube')
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
            data = r.json()
            print(data)
            if data['pageInfo']['totalResults']:
                print(data["pageInfo"])
            else:
                return None
                
        else:
            print(r.text)
            print(r.status_code)

    def get_channel_content(self,channel_id:str):
        '''獲取Youtube頻道資訊'''
        params = {
            'key': self.__token,
            'id':channel_id,
            #'forUsername': channel_name,
            'part': 'statistics,snippet',
            'maxResults':1
        }
        r = requests.get('https://youtube.googleapis.com/youtube/v3/channels',params=params)
        if r.status_code == 200:
            return YoutubeChannel(r.json().get('items')[0])
        else:
            return None

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

    def get_stream(self,channel_id:str):
        '''取得Youtube直播資訊（若無正在直播則回傳None）'''
        params ={
            'key': self.__token,
            'part': 'snippet',
            'channelId': channel_id,
            'eventType':'live',
            'type': 'video'
        }
        r = requests.get('https://www.googleapis.com/youtube/v3/search',params=params)
        if r.status_code == 200 and r.json()['items']:
            return YouTubeStream(r.json()['items'][0])
        else:
            print(r.text)
            print(r.status_code)
            return None