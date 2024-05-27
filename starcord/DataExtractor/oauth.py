from datetime import datetime, timedelta

import requests

from ..models import UserConnection
from ..types import CommunityType
from ..Database import sqldb
from ..errors import SQLNotFoundError

class DiscordOauth:
    """
    Represents a Discord OAuth client for handling authentication and API requests.

    Parameters:
    - client_id (str): The client ID of the Discord application.
    - client_secret (str): The client secret of the Discord application.
    - redirect_uri (str, optional): The redirect URI for the OAuth flow. Defaults to 'http://127.0.0.1:14000/discord '.
    - user_id (int, optional): The user ID associated with the OAuth token. Defaults to None.\n
    - if provided, the OAuth token will be set automatically from database.

    Attributes:
    - API_ENDPOINT (str): The Discord API endpoint.
    - CLIENT_ID (str): The client ID of the Discord application.
    - CLIENT_SECRET (str): The client secret of the Discord application.
    - REDIRECT_URI (str): The redirect URI for the OAuth flow.
    - expires_at (datetime): The expiration date and time of the access token.
    """

    API_ENDPOINT = 'https://discord.com/api/v9'

    def __init__(self, client_id:str, client_secret:str, redirect_uri='http://127.0.0.1:14000/discord', user_id:int=None):
        self.CLIENT_ID = client_id
        self.CLIENT_SECRET = client_secret
        self.REDIRECT_URI = redirect_uri
        self.expires_at = None
        self._user_id = user_id
        if user_id:
            self.set_token(user_id)

    @property
    def user_id(self):
        if self._user_id is None:
            self._user_id = self.get_me()['id']
        return self._user_id

    def set_token(self, user_id):
        """
        Set the OAuth token for the specified user ID.

        Parameters:
        - user_id (str): The user ID.

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


    def save_token(self):
        """
        Save the OAuth token to the database.
        """
        sqldb.set_oauth(self.user_id, CommunityType.Discord, self.access_token, self.refresh_token, self.expires_at)

    def refresh_access_token(self) -> dict:
        """
        Refreshes the access token using the refresh token.

        Parameters:
        - refresh_token (str): The refresh token.

        Returns:
        - dict: The JSON response containing the new access token.
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
        if sqldb:
            self.save_token()
        return data

    def exchange_code(self, code) -> dict:
        """
        Exchanges the authorization code for an access token.
        You can get the code from the query parameter 'code' in the redirect URI.
        
        Parameters:
        - code (str): The authorization code.

        Returns:
        - dict: The JSON response containing the access token.
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
        if sqldb:
            self.save_token()
        return data

    def get_me(self) -> dict:
        """
        Retrieves the user information.

        Returns:
        - dict: The JSON response containing the user information.
        """
        headers = {
            'Authorization': f'Bearer {self.access_token}'
        }
        r = requests.get('%s/users/@me' % self.API_ENDPOINT, headers=headers)
        return r.json()
    
    def get_connections(self) -> list[UserConnection] | None:
        """
        Retrieves the user connections.

        This method sends a GET request to the Discord API to retrieve the user's connections.
        It requires the user to be authenticated with an access token.

        Returns:
        - list: A list of UserConnection objects representing the user's connections.
        """
        headers = {
            'Authorization': f'Bearer {self.access_token}'
        }
        r = requests.get('%s/users/@me/connections' % self.API_ENDPOINT, headers=headers)
        if r.ok:
            data = r.json()
            return [UserConnection(i) for i in data]
