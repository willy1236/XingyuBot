from datetime import datetime, timedelta

import requests

from ..database import sqldb
from ..errors import SQLNotFoundError
from ..models import DiscordUser, UserConnection
from ..types import CommunityType


class BaseOauth:
    """
    Base class for handle OAuth authentication.
    """
    
    def __init__(self, settings:dict) -> None:
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

    def save_token(self, user_id, type:CommunityType):
        if sqldb:
            type = CommunityType(type)
            sqldb.set_oauth(user_id, type, self.access_token, self.refresh_token, self.expires_at)

class DiscordOauth(BaseOauth):
    """
    Represents a Discord OAuth client for handling authentication and API requests.
    """

    API_ENDPOINT = 'https://discord.com/api/v9'

    def __init__(self, settings:dict, user_id:int=None):
        super().__init__(settings)
        if self.REDIRECT_URI is None:
            self.REDIRECT_URI = 'http://127.0.0.1:14000/discord'

        self._user_id = user_id
        
        if user_id:
            self.set_token_from_id(user_id)

    @property
    def user_id(self):
        if self._user_id is None:
            self._user_id = self.get_me().id
        return self._user_id

    def set_token_from_id(self, user_id):
        """
        Set the OAuth token for the specified user ID.

        Raises:
        - SQLNotFoundError: If the Discord OAuth token is not found in the database.
        """
        dbdata = sqldb.get_oauth(user_id, CommunityType.Discord)
        if not dbdata:
            raise SQLNotFoundError(f'Discord OAuth token not found. ({user_id=})')
        
        self._user_id = user_id
        self.access_token = dbdata['access_token']
        self.refresh_token = dbdata['refresh_token']
        self.expires_at = dbdata['expires_at']
        
        if dbdata['expires_at'] < datetime.now():
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
        super().__init__(settings)
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