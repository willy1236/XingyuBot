import os
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from ..database import sqldb
from ..errors import SQLNotFoundError
from ..models import DiscordUser, UserConnection
from ..types import CommunityType


class BaseOauth:
    """
    Base class for handle OAuth authentication.
    """
    if TYPE_CHECKING:
        headers: dict[str, str]
        CLIENT_ID: str | None
        CLIENT_SECRET: str | None
        REDIRECT_URI: str | None

        access_token: str | None
        refresh_token: str | None
        expires_at: datetime | None
        
    def __init__(self, **settings) -> None:
        """
        Parameters:
        - settings (dict): 包含id, secret, redirect_uri，未提供的項目會設為None
        """
        self.headers = {}
        self.CLIENT_ID = settings.get("id")
        self.CLIENT_SECRET = settings.get("secret")
        self.REDIRECT_URI = settings.get("redirect_uri")
        
        self.access_token = None
        self.refresh_token = None
        self.expires_at = None

    @property
    def expired(self) -> bool:
        return not (self.expires_at and self.expires_at > datetime.now())

    def save_token(self, user_id, type:CommunityType):
        """
        將OAuth token存入資料庫。
        """
        if sqldb:
            type = CommunityType(type)
            sqldb.set_oauth(user_id, type, self.access_token, self.refresh_token, self.expires_at)

    def _set_token_from_db(self, type:CommunityType, user_id:int):
        """
        從資料庫取得指定使用者的OAuth token。
        """
        dbdata = sqldb.get_oauth(user_id, CommunityType.Google)
        if not dbdata:
            raise SQLNotFoundError(f'token not found. ({type=}, {user_id=})')
        
        self.access_token = dbdata.access_token
        self.refresh_token = dbdata.refresh_token
        self.expires_at = dbdata.expires_at

class DiscordOauth(BaseOauth):
    """
    Represents a Discord OAuth client for handling authentication and API requests.
    """

    API_ENDPOINT = 'https://discord.com/api/v9'

    def __init__(self, settings:dict, user_id:int=None):
        super().__init__(**settings)
        if self.REDIRECT_URI is None:
            self.REDIRECT_URI = 'http://127.0.0.1:14000/discord'

        self._user_id = user_id
        
        if user_id:
            self._set_token_from_db(user_id)

    @property
    def user_id(self):
        if self._user_id is None:
            self._user_id = self.get_me().id
        return self._user_id

    def _set_token_from_db(self, user_id):
        """
        Set the OAuth token for the specified user ID.

        Raises:
        - SQLNotFoundError: If the Discord OAuth token is not found in the database.
        """
        self._set_token_from_db(CommunityType.Discord, user_id)
        
        if self.expired:
            self.refresh_access_token()

        self.headers["Authorization"] = f'Bearer {self.access_token}'

    def refresh_access_token(self) -> dict:
        """
        Refreshes the access token using the refresh token.
        """
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token
        }
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        r = requests.post('%s/oauth2/token' % self.API_ENDPOINT, data=data, headers=headers, auth=(self.CLIENT_ID, self.CLIENT_SECRET))
        r.raise_for_status()
        data = r.json()
        
        self.access_token = data['access_token']
        self.refresh_token = data['refresh_token']
        self.expires_at = datetime.now() + timedelta(seconds=data['expires_in'])
        
        self.save_token(self.user_id,CommunityType.Discord)
        return data

    def exchange_code(self, code) -> dict:
        """
        Exchanges the authorization code for an access token.
        You can get the code from the query parameter 'code' in the redirect URI.
        """
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': self.REDIRECT_URI
        }
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        r = requests.post('%s/oauth2/token' % self.API_ENDPOINT, data=data, headers=headers, auth=(self.CLIENT_ID, self.CLIENT_SECRET))
        r.raise_for_status()
        data = r.json()
        
        self.access_token = data['access_token']
        self.refresh_token = data['refresh_token']
        self.expires_at = datetime.now() + timedelta(seconds=data['expires_in'])
        self.headers["Authorization"] = f'Bearer {self.access_token}'
        
        self.save_token(self.user_id, CommunityType.Discord)
        return data

    def get_me(self) -> DiscordUser:
        """
        Retrieves the user information. 
        """
        r = requests.get('%s/users/@me' % self.API_ENDPOINT, headers=self.headers)
        return DiscordUser(**r.json())
    
    def get_connections(self) -> list[UserConnection | None]:
        """
        Retrieves the user connections.
        """
        r = requests.get('%s/users/@me/connections' % self.API_ENDPOINT, headers=self.headers)
        if r.ok:
            data = r.json()
            return [UserConnection(**i) for i in data]
        

class TwitchOauth(BaseOauth):
    """
    Represents a Twitch OAuth client for handling authentication and API requests.
    """

    API_ENDPOINT = 'https://api.twitch.tv/helix'

    def __init__(self, settings:dict, user_id:int=None):
        super().__init__(**settings)
        self.headers["Client-Id"] = self.CLIENT_ID
        self._user_id = user_id

    @property
    def user_id(self):
        if self._user_id is None:
            try:
                apidata = self.get_user()
                self._user_id = apidata['data'][0]['id']
            except KeyError:
                print(apidata)
                raise
        return self._user_id

    def exchange_code(self, code) -> dict:
        """
        Exchanges the authorization code for an access token.
        You can get the code from the query parameter 'code' in the redirect URI.
        """
        data = {
            'grant_type': 'authorization_code',
            'client_id': self.CLIENT_ID,
            'client_secret': self.CLIENT_SECRET,
            'code': code,
            'redirect_uri': self.REDIRECT_URI
        }
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        r = requests.post("https://id.twitch.tv/oauth2/token", data=data, headers=headers, auth=(self.CLIENT_ID, self.CLIENT_SECRET))
        r.raise_for_status()
        data = r.json()
        
        self.access_token = data['access_token']
        self.refresh_token = data['refresh_token']
        self.expires_at = datetime.now() + timedelta(seconds=data['expires_in'])
        self.headers["Authorization"] = f'Bearer {self.access_token}'
        
        self.save_token(self.user_id, CommunityType.Twitch)
        return data
    
    def get_user(self) -> dict:
        """
        Retrieves the user information.
        """
        r = requests.get(f'{self.API_ENDPOINT}/users', headers=self.headers)
        return r.json()
    
class GoogleOauth(BaseOauth):
    def __init__(self, settings:dict=None, user_id:int=None):
        super().__init__(**settings)
        self._user_id = user_id
        
        self.creds = self.get_creds()
            
    def get_creds(self):
        SCOPES = ['https://www.googleapis.com/auth/youtube']
        creds = self.get_cred_from_db(self._user_id)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'database/google_client_credentials.json', SCOPES)
                creds = flow.run_local_server()
            
                self.access_token = creds.token
                self.refresh_token = creds.refresh_token
                self.expires_at = creds.expiry
                self.save_token(self._user_id, CommunityType.Google)
        return creds
    
    def get_cred_from_db(self, user_id):
        try:
            self._set_token_from_db(CommunityType.Google, user_id)
            return Credentials(token=self.access_token, refresh_token=self.refresh_token, expiry=self.expires_at)
        except SQLNotFoundError:
            return None
        

    def get_mine_channel(self):
        service = build('youtube', 'v3', credentials=self.creds)
        results = service.channels().list(mine=True, part='snippet').execute()
        return results
    
    def list_playlists(self):
        service = build('youtube', 'v3', credentials=self.creds)
        results = service.playlists().list(part='snippet', mine=True).execute()
        return results
    
    def get_playlist_item(self, playlist_id, nextPageToken=None):
        service = build('youtube', 'v3', credentials=self.creds)
        if isinstance(nextPageToken, str):
            results = service.playlistItems().list(part='snippet', playlistId=playlist_id, pageToken=nextPageToken, maxResults=50).execute()
        else:
            results = service.playlistItems().list(part='snippet', playlistId=playlist_id, maxResults=50).execute()
        return results
    
    def add_song_to_playlist(self, playlist_id, video_id):
        service = build('youtube', 'v3', credentials=self.creds)
        request = service.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {
                        "kind": "youtube#video",
                        "videoId": video_id
                    }
                }
            }
        )
        return request.execute()
    
    def remove_song_from_playlist(self, video_in_playlist_id):
        service = build('youtube', 'v3', credentials=self.creds)
        request = service.playlistItems().delete(id=video_in_playlist_id)
        return request.execute()