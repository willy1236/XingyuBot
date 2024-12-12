import os.path
from datetime import timezone

import feedparser
import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from ..errors import APIInvokeError, Forbidden
from ..fileDatabase import Jsondb
from ..models.community import *


class TwitchAPI():
    '''
    與Twitch api交互相關
    '''
    BaseURL = "https://api.twitch.tv/helix"

    def __init__(self):
        self._headers = self.__get_headers()    

    def __get_headers(self):
        TOKENURL = "https://id.twitch.tv/oauth2/token"
        #headers = {"Content-Type": "application/x-www-form-urlencoded"}
        tokens = Jsondb.get_token("twitch_chatbot")
        params = {
            'client_id':tokens["id"],
            'client_secret':tokens["secret"],
            'grant_type':'client_credentials'
            }

        r = requests.post(TOKENURL, params=params)
        apidata = r.json()
        if r.ok:
            headers = {
                'Authorization': f"Bearer {apidata['access_token']}",
                'Client-Id':tokens["id"]
            }
            return headers
        else:
            raise Forbidden(f"在讀取Twitch API時發生錯誤",f"[{r.status_code}] {apidata['message']}")

    def get_lives(self,users:str | list[str], use_user_logins=False) -> dict[str, TwitchStream | None]:
        """
        取得twitch用戶的直播資訊
        :param users: list of users id
        :return: dict: {user_id: TwitchStream | None（如果無正在直播）}
        """
        params = {
            "first": 1
        }
        if use_user_logins:
            params["user_login"] = users
        else:
            params["user_id"] = users
        r = requests.get(f"{self.BaseURL}/streams", params=params,headers=self._headers)
        apidata = r.json()
        dict = {}
        
        if not isinstance(users, list):
            users = [users]

        for user in users:
            dict[user] = None

        for data in apidata['data']:
            if use_user_logins:
                dict[data.get('user_login')] = TwitchStream(**data)
            else:
                dict[data.get('user_id')] = TwitchStream(**data)
        
        return dict

    def get_user(self,username:str) -> TwitchUser | None:
        """
        取得Twitch用戶
        :param username: 用戶名稱（user_login）
        """
        params = {
            "login": username,
            "first": 1
        }
        r = requests.get(f"{self.BaseURL}/users", params=params,headers=self._headers)
        apidata = r.json()
        if apidata.get('data'):
            return TwitchUser(**apidata['data'][0])
        else:
            return None
        
    def get_user_by_id(self,userid:str) -> TwitchUser | None:
        """
        取得Twitch用戶
        :param userid: 用戶id（user_id）
        """
        params = {
            "id": userid,
            "first": 1
        }
        r = requests.get(f"{self.BaseURL}/users", params=params,headers=self._headers)
        apidata = r.json()
        if apidata.get('data'):
            return TwitchUser(**apidata['data'][0])
        else:
            return None

    def get_videos(self, user_ids:str|list[str] = None, ids:str|list[str] = None, types:str|list[str]="highlight"):
        """
        取得twitch用戶的影片資訊
        :param users: list of users id
        :return: list[TwitchVideo]
        """
        params = {
            "sort": "time",
            "first": 5,
            "type": types
        }

        if user_ids:
            params["user_id"] = user_ids
        elif ids:
            params["id"] = ids
        else:
            raise ValueError("must provide either user_ids or ids.")

        r = requests.get(f"{self.BaseURL}/videos", params=params,headers=self._headers)
        apidata = r.json()
        if apidata.get('data'):
            return [TwitchVideo(**i) for i in apidata['data']]
        else:
            return None


    def get_clips(self,broadcaster_id:int,started_at:datetime=None):
        """
        取得twitch用戶的剪輯資訊\\
        *即使加入了started_at參數，Twitch API也會返回指定時間之前的clip，原因未知，需手動過濾資料*
        """
        params = {
            "broadcaster_id": broadcaster_id,
            "first": 5,
        }
        if started_at:
            params['started_at'] = started_at.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            params['ended_at'] = datetime.now(tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        
        r = requests.get(f"{self.BaseURL}/clips", params=params,headers=self._headers)
        apidata = r.json()
        if apidata.get('data'):
            return [clip for clip in [TwitchClip(**i) for i in apidata['data']] if clip.created_at > started_at]
        else:
            return None

class YoutubeAPI():
    BaseURL = "https://www.googleapis.com/youtube/v3"
    
    def __init__(self):
        self.__token = Jsondb.get_token("youtube_api")
        self.__headers = {
            'x-goog-api-key': self.__token,
            'Accept': 'application/json'
        }

    def get_channel_id(self, channel_handle: str) -> str | None:
        """
        Retrieves the channel ID for a given channel handle.

        Args:
            channel_handle (str): The handle of the channel.

        Returns:
            str | None: The ID of the channel if found, None otherwise.
        """
        params = {
            'forHandle': channel_handle,
            'part': 'id',
            'maxResults': 1
        }
        r = requests.get(f'{self.BaseURL}/channels', params=params, headers=self.__headers)
        if r.ok:
            data = r.json()
            if data['pageInfo']['totalResults']:
                return data["items"][0]['id']
            else:
                return None
        else:
            print(r.text)
            print(r.status_code)

    def get_channel(self, id:str=None, handle:str=None):
        '''獲取Youtube頻道資訊
        :param id: 頻道ID
        :param handle: 頻道名稱
        兩者擇一提供即可
        '''
        params = {
            'id':id,
            'forHandle': handle,
            'part': 'statistics,snippet',
            'maxResults':1
        }
        r = requests.get(f'{self.BaseURL}/channels', params=params, headers=self.__headers)
        if r.ok:
            return YoutubeChannel(**r.json().get('items')[0]) if r.json().get('items') else None
        else:
            raise APIInvokeError("youtube_get_video", f"[{r.status_code}] {r.text}")

    def get_channelsection(self,channel_id:str):
        params = {
            'key': self.__token,
            'channelId': channel_id,
            'part': 'contentDetails'
        }
        r = requests.get(f'{self.BaseURL}/channelSections',params=params)
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
        r = requests.get(f'{self.BaseURL}/search',params=params)
        if r.ok:
            print(r)
            print(r.json())
        else:
            print(r.text)
            print(r.status_code)

    def get_stream(self,channel_id:str):
        '''取得Youtube直播資訊（若無正在直播則回傳None）'''
        params ={
            'part': 'snippet',
            'channelId': channel_id,
            'eventType':'live',
            'type': 'video'
        }
        r = requests.get(f'{self.BaseURL}/search', params=params, headers=self.__headers)
        if r.ok:
            return YouTubeStream(**r.json()['items'][0]) if r.json()['items'] else None
        else:
            raise APIInvokeError("youtube_get_stream", f"[{r.status_code}] {r.text}")
        
    def get_video(self,video_id:str|list) -> list[YoutubeVideo]:
        params ={
            'part': 'snippet,liveStreamingDetails',
            'id': video_id
        }
        r = requests.get(f'{self.BaseURL}/videos', params=params, headers=self.__headers)
        if r.ok:
            return [YoutubeVideo(**i) for i in r.json()['items']] if r.json()['items'] else list()
        else:
            raise APIInvokeError("youtube_get_video", f"[{r.status_code}] {r.text}")
        
    def get_playlist(self,playlist_id:str|list):
        params ={
            'key': self.__token,
            'part': 'snippet,contentDetails',
            'id': playlist_id
        }
        r = requests.get(f'{self.BaseURL}/playlists',params=params)
        if r.ok:
            return r.json()['items'][0] if r.json()['items'] else None
        else:
            print(r.text)
            print(r.status_code)
            return None
    
    def get_playlist_item(self,playlist_id:str|list):
        params ={
            'key': self.__token,
            'part': 'snippet,contentDetails',
            'playlistId': playlist_id
        }
        r = requests.get(f'{self.BaseURL}/playlistItems',params=params)
        if r.ok:
            return r.json()['items'][0] if r.json()['items'] else None
        else:
            print(r.text)
            print(r.status_code)
            return None

class YoutubeRSS():
    def get_videos(self,channel_id) -> list[YoutubeRSSVideo]:
        """從RSS取得影片（由新到舊）"""
        feed = feedparser.parse(f'https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}')
        # for entry in feed['entries']:
        #     print(entry)
        return [YoutubeRSSVideo(**i) for i in feed['entries']]

class GoogleCloud():
    def __init__(self):
        self.creds = self.get_creds()
    
    def get_creds(self):
        # If modifying these scopes, delete the file token.json.
        SCOPES = ['https://www.googleapis.com/auth/drive']
        # The file token.json stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        creds = None
        if os.path.exists('database/google_token.json'):
            creds = Credentials.from_authorized_user_file('database/google_token.json', SCOPES)
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'database/credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open('database/google_token.json', 'w') as token:
                token.write(creds.to_json())
        return creds
    
    def list_drive_files(self):
        """Shows basic usage of the Drive v3 API.
        Prints the names and ids of the first 10 files the user has access to.
        """

        try:
            service = build('drive', 'v3', credentials=self.creds)

            # Call the Drive v3 API
            results = service.files().list(
                pageSize=10, fields="nextPageToken, files(id, name)").execute()
            items = results.get('files', [])

            if not items:
                print('No files found.')
                return
            print('Files:')
            for item in items:
                print(u'{0} ({1})'.format(item['name'], item['id']))
            return results
        except HttpError as error:
            print(f'An error occurred: {error}')

    def list_file_permissions(self,fileId):
        service = build('drive', 'v3', credentials=self.creds)
        results = service.permissions().list(fileId=fileId).execute()
        print(results)
        return results

    def add_file_permissions(self,fileId,emailAddress):
        service = build('drive', 'v3', credentials=self.creds)
        permission_dict = {
        "role": "reader",
        'type': 'user',
        'emailAddress': emailAddress
        }
        results = service.permissions().create(fileId=fileId,body=permission_dict).execute()
        print(results)
        return results
    
    def remove_file_permissions(self,fileId,permissionId):
        service = build('drive', 'v3', credentials=self.creds)
        results = service.permissions().delete(fileId=fileId,permissionId=permissionId).execute()
        print(results)
        return results

class NotionAPI():
    def __init__(self):
        self.headers = self._get_headers()
        self.url = "https://api.notion.com/v1"

    def _get_headers(self):
        token = Jsondb.get_token("notion_api")
        return {
            "Authorization": f"Bearer {token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }
    
    def get_page(self,page_id:str):
        r = requests.get(f"{self.url}/pages/{page_id}",headers=self.headers)
        apidata = r.json()
        if r.status_code == 200:
            print(apidata)
        else:
            print(apidata['message'])
    
    def get_block(self,block_id:str):
        r = requests.get(f"{self.url}/blocks/{block_id}",headers=self.headers)
        apidata = r.json()
        if r.status_code == 200:
            print(apidata)
        else:
            print(apidata['message'])
    
    def search(self,title:str):
        """search by title"""
        data = {
            "query": title
        }
        r = requests.post(f"{self.url}/search",json=data,headers=self.headers)
        apidata = r.json()
        if r.status_code == 200:
            print(apidata)
        else:
            print(apidata['message'])