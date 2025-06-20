from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING
from urllib.parse import urlencode

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from ..database import debug_mode, sqldb
from ..errors import SQLNotFoundError
from ..models import DiscordUser, UserConnection
from ..models.mysql import BotToken
from ..settings import tz
from ..types import CommunityType
from ..utils import log


class OAuth2Base(ABC):
    def __init__(self, client_id, client_secret, redirect_uri, scopes=None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

        self.scopes = scopes
        self.access_token = None
        self.refresh_token = None
        self.expires_at = None

    @property
    @abstractmethod
    def api_url(self):
        """API 網址"""
        pass

    @property
    @abstractmethod
    def auth_url(self):
        """授權網址"""
        pass

    @property
    @abstractmethod
    def token_url(self):
        """交換 token 的網址"""
        pass

    @property
    @abstractmethod
    def community_type(self) -> CommunityType:
        """社群類型"""
        pass

    @abstractmethod
    def get_me(self):
        """取得使用者資訊（由各平台自行實作）"""
        pass

    @property
    def expired(self):
        return not (self.expires_at and self.expires_at > datetime.now(tz))

    def get_authorization_url(self, state=None, **kwargs):
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
        }
        if self.scopes:
            params["scope"] = self.scopes
        if state:
            params["state"] = state

        return f"{self.auth_url}?{urlencode(params | kwargs, safe='+')}"
        # return f"{self.auth_url}?{join(params)}"

    def exchange_code(self, code: str):
        """
        Exchange an authorization code for an access token.
        This method sends a POST request to the token URL with the authorization code
        and other required parameters to obtain an access token from the OAuth provider.
        Args:
            code (str): The authorization code received from the OAuth provider
                        after user authorization.
        Returns:
            dict: The complete token response data from the OAuth provider,
                  which typically includes:
                  - access_token: Token to access protected resources
                  - refresh_token: Token to obtain a new access token when the current one expires
                  - expires_in: Token lifetime in seconds
                  - scope: Granted permission scopes
        Raises:
            HTTPError: If the request to the token endpoint fails
        Side Effects:
            - Sets self.access_token with the received access token
            - Sets self.refresh_token with the received refresh token
            - Sets self.expires_at with the calculated expiration datetime
            - Sets self.scopes with the granted permission scopes
        """
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        headers = {"Accept": "application/x-www-form-urlencoded"}
        response = requests.post(self.token_url, data=data, headers=headers)
        response.raise_for_status()

        token_data = response.json()
        self.access_token = token_data.get("access_token")
        self.refresh_token = token_data.get("refresh_token")
        self.expires_at = datetime.now(tz) + timedelta(seconds=token_data.get("expires_in", 0))
        self.scopes = token_data.get("scope")
        return token_data

    def get(self, url, params: dict = None, with_client_id=False):
        if not self.access_token:
            raise Exception("Access token not available.")
        headers = {"Authorization": f"Bearer {self.access_token}"}
        if with_client_id:
            headers["Client-Id"] = self.client_id
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()

    def load_token_from_db(self, user_id):
        """
        從資料庫取得指定使用者的OAuth token。
        """
        dbdata = sqldb.get_oauth(user_id, self.community_type)
        if not dbdata:
            raise SQLNotFoundError(f"token not found. ({user_id=}, {self.community_type=})")

        self.access_token = dbdata.access_token
        self.refresh_token = dbdata.refresh_token
        self.expires_at = dbdata.expires_at

        if self.expired:
            self.refresh()

    def save_token(self, user_id):
        """
        將OAuth token存入資料庫。
        """
        if sqldb:
            sqldb.set_oauth(user_id, self.community_type, self.access_token, self.refresh_token, self.expires_at)
        else:
            log.warning(f"sqldb not found, token not saved. ({user_id=}, {self.community_type=})")

    def refresh(self):
        """
        Refresh the access token using the refresh token.
        """
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        headers = {"Accept": "application/x-www-form-urlencoded"}
        response = requests.post(self.token_url, data=data, headers=headers)
        response.raise_for_status()

        token_data = response.json()
        self.access_token = token_data.get("access_token")
        self.refresh_token = token_data.get("refresh_token")
        self.expires_at = datetime.now(tz) + timedelta(seconds=token_data.get("expires_in", 0))
        self.scopes = token_data.get("scope")
        return token_data

    @classmethod
    def from_bot_token(cls, bot_token: BotToken, as_bot=False):
        """
        從資料庫設定機器人的OAuth client config。

        Args:
            bot_token (BotToken): 機器人token物件
            as_bot (bool, optional): 帶入資料庫中機器人身分的access_token等。 預設為 False
        """
        instance = cls(client_id=bot_token.client_id, client_secret=bot_token.client_secret, redirect_uri=bot_token.redirect_uri)

        if as_bot:
            instance.access_token = bot_token.access_token
            instance.refresh_token = bot_token.refresh_token
            instance.expires_at = bot_token.expires_at

        # if instance.expired:
        #     instance.refresh()

        return instance

class DiscordOauth2(OAuth2Base):
    auth_url = "https://discord.com/api/oauth2/authorize"
    token_url = "https://discord.com/api/oauth2/token"
    api_url = "https://discord.com/api/v9"
    community_type = CommunityType.Discord

    def __init__(self, client_id, client_secret, redirect_uri="http://127.0.0.1:14000/oauth/discord", scope=None, user_id=None):
        super().__init__(client_id, client_secret, redirect_uri, scope)
        self._user_id = user_id
        if user_id:
            self.load_token_from_db(user_id)

    @property
    def user_id(self):
        if self._user_id is None:
            self._user_id = self.get_me().id
        return self._user_id

    def get_me(self):
        """
        Retrieves the user information.
        """
        return DiscordUser(**self.get(f"{self.api_url}/users/@me"))

    def get_connections(self) -> list[UserConnection | None]:
        """
        Retrieves the user connections.
        """
        return [UserConnection(**i) for i in self.get(f"{self.api_url}/users/@me/connections")]

class TwitchOauth2(OAuth2Base):
    auth_url = "https://id.twitch.tv/oauth2/authorize"
    token_url = "https://id.twitch.tv/oauth2/token"
    api_url = "https://api.twitch.tv/helix"
    community_type = CommunityType.Twitch

    def __init__(self, client_id, client_secret, redirect_uri="http://localhost:14000/oauth/twitch", scope=None, user_id=None):
        super().__init__(client_id, client_secret, redirect_uri, scope)
        self._user_id = user_id
        if user_id:
            self.load_token_from_db(user_id)

    @property
    def user_id(self):
        if self._user_id is None:
            try:
                apidata = self.get_user()
                self._user_id = apidata["data"][0]["id"]
            except KeyError:
                print(apidata)
                raise
        return self._user_id

    def get_me(self):
        return self.get_user()

    def validate_token(self):
        """
        Validate the access token.
        """
        headers = {
            "Authorization": f"OAuth {self.access_token}",
        }
        r = requests.get(f"https://id.twitch.tv/oauth2/validate", headers=headers)
        if r.status_code == 200:
            data = r.json()
            self._user_id = data.get("user_id")
            self.scope = data.get("scope")
            return data
        else:
            r.raise_for_status()

    def get_user(self, user_id=None) -> dict:
        """
        Retrieves the user information.
        """
        param = {"id": self.user_id} if user_id else None
        return self.get(f"{self.api_url}/users", params=param, with_client_id=True)


class GoogleOauth2(OAuth2Base):
    auth_url = "https://accounts.google.com/o/oauth2/auth"
    token_url = "https://oauth2.googleapis.com/token"
    api_url = "https://www.googleapis.com/oauth2/v1"
    community_type = CommunityType.Google

    def __init__(self, client_id=None, client_secret=None, redirect_uri="https://localhost:14000/oauth/google", scopes=None, user_id=None):
        if not client_id or not client_secret:
            token = sqldb.get_bot_token(CommunityType.Google, 3)
            client_id = token.client_id
            client_secret = token.client_secret

        super().__init__(client_id, client_secret, redirect_uri, scopes)
        self._user_id = user_id
        self._creds = None

    @property
    def creds(self) -> Credentials:
        if self._creds is None:
            self.set_creds()
        elif self._creds.expired and self._creds.refresh_token:
            self._creds.refresh(Request())
            self.access_token = self._creds.token
            self.refresh_token = self._creds.refresh_token
            self.expires_at = self._creds.expiry.replace(tzinfo=timezone(timedelta(hours=0))).astimezone(tz)
            self.save_token(self.user_id)
        return self._creds  # type: ignore

    @property
    def user_id(self):
        if self._user_id is None:
            try:
                apidata = self.get_me()
                self._user_id = apidata["id"]
            except KeyError:
                print(apidata)
                raise
        return self._user_id

    def set_creds(self, creds=None):
        """
        設定 Google OAuth2 的憑證。\\
        會依user_id、傳入的 creds、access_token 的順序來取得憑證。\\
        如果都沒有且在debug_mode下，則會從 Google OAuth2 隱式授權中取得 token。
        """
        if self._user_id:
            self.load_token_from_db(self._user_id)
            self._creds = Credentials(token=self.access_token, refresh_token=self.refresh_token, expiry=self.expires_at.replace(tzinfo=None))
        elif creds:
            self._creds = creds
        elif self.access_token:
            self._creds = Credentials(token=self.access_token, refresh_token=self.refresh_token, expiry=self.expires_at.replace(tzinfo=None))

        if debug_mode and (not self._creds or not self._creds.valid):
            if self._creds and self._creds.expired and self._creds.refresh_token:
                self._creds.refresh(Request())
            else:
                # flow = InstalledAppFlow.from_client_secrets_file(
                #     'database/google_client_credentials.json', self.scopes)
                client_config = sqldb.get_google_client_config(3)
                flow = InstalledAppFlow.from_client_config(client_config, self.scopes)
                self._creds = flow.run_local_server()

                self.access_token = self._creds.token
                self.refresh_token = self._creds.refresh_token
                self.expires_at = self._creds.expiry.replace(tzinfo=timezone(timedelta(hours=0))).astimezone(tz)
                self.save_token(self.user_id)

    def get_me(self):
        return self.get(f"{self.api_url}/userinfo")

    def get_user(self, user_id="me"):
        service = build("people", "v1", credentials=self.creds)
        results = service.people().get(resourceName=f"people/{user_id}", personFields="names,emailAddresses").execute()
        return results

    def get_mine_channel(self):
        service = build("youtube", "v3", credentials=self.creds)
        results = service.channels().list(mine=True, part="snippet").execute()
        return results

    def list_playlists(self):
        service = build("youtube", "v3", credentials=self.creds)
        results = service.playlists().list(part="snippet", mine=True).execute()
        return results

    def get_playlist_item(self, playlist_id, nextPageToken=None):
        service = build("youtube", "v3", credentials=self.creds)
        if isinstance(nextPageToken, str):
            results = service.playlistItems().list(part="snippet", playlistId=playlist_id, pageToken=nextPageToken, maxResults=50).execute()
        else:
            results = service.playlistItems().list(part="snippet", playlistId=playlist_id, maxResults=50).execute()
        return results

    def add_song_to_playlist(self, playlist_id, video_id):
        service = build("youtube", "v3", credentials=self.creds)
        request = service.playlistItems().insert(
            part="snippet", body={"snippet": {"playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}}}
        )
        return request.execute()

    def remove_song_from_playlist(self, video_in_playlist_id):
        service = build("youtube", "v3", credentials=self.creds)
        request = service.playlistItems().delete(id=video_in_playlist_id)
        return request.execute()
