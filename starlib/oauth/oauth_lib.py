# oauth_lib.py
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import TypedDict

from authlib.integrations.httpx_client import AsyncOAuth2Client
from ..models.mysql import OAuth2Token, BotToken
from ..types import CommunityType
from ..database import sqldb


class OAuthTokenData(TypedDict, total=False):
    access_token: str
    refresh_token: str | None
    token_type: str
    expires_in: int
    scope: str | None


class OAuth2Base(ABC):
    client: AsyncOAuth2Client

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str, scopes: str | None = None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scopes = scopes
        self.db_token: OAuth2Token | None = None

    # ====== 子類別要提供的 ======
    @property
    @abstractmethod
    def auth_url(self) -> str: ...

    @property
    @abstractmethod
    def token_url(self) -> str: ...

    @property
    @abstractmethod
    def api_url(self) -> str: ...

    @property
    @abstractmethod
    def community_type(self) -> CommunityType: ...

    # ====== Authlib OAuth Client ======
    @property
    def oauth_client(self) -> AsyncOAuth2Client:
        return AsyncOAuth2Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            scope=self.scopes,
        )

    # ====== Authorization URL ======
    def get_authorization_url(self) -> str:
        client = self.oauth_client
        uri, _ = client.create_authorization_url(self.auth_url)
        return uri

    # ====== Basic functions ======
    async def exchange_code(self, code: str) -> OAuthTokenData:
        """
        Exchange an authorization code for an OAuth token.
        It won't save the token to the database; you need to call `save_token_to_db` yourself.

        Args:
            code (str): The authorization code received from the OAuth provider
                after user authorization.
        Returns:
            OAuthTokenData: An object containing the OAuth token data, typically
                including access_token, token_type, expires_in, refresh_token,
                and scope.
        Raises:
            OAuthError: If the token exchange fails due to invalid code,
                expired code, or other OAuth-related errors.
            NetworkError: If there are network-related issues during the
                token exchange request.

        """

        client = self.oauth_client
        token = await client.fetch_token(
            url=self.token_url,
            code=code,
            redirect_uri=self.redirect_uri,
        )
        return token

    async def refresh(self, refresh_token: str) -> OAuthTokenData:
        client = self.oauth_client
        token = await client.refresh_token(
            url=self.token_url,
            refresh_token=refresh_token,
        )
        return token

    def has_scope(self, scope: str) -> bool:
        if not self.scopes:
            return False
        return scope in self.scopes.split(" ")

    # ====== Signed GET/POST ======
    async def api_get(self, token: OAuthTokenData, path: str, params: dict | None = None):
        client = self.oauth_client
        client.token = token
        resp = await client.get(f"{self.api_url}{path}", params=params)
        resp.raise_for_status()
        return resp.json()

    # ====== Token DB Integration ======
    @classmethod
    def create_from_db(cls, bot_token: BotToken, scopes: str | None = None):
        instance = cls(client_id=bot_token.client_id, client_secret=bot_token.client_secret, redirect_uri=bot_token.redirect_uri, scopes=scopes)
        return instance

    def load_token_from_db(self, user_id: str) -> OAuth2Token:
        token = sqldb.get_oauth(user_id, self.community_type)
        if not token:
            raise Exception("OAuth token not found.")
        self.db_token = token
        return token

    def save_token_to_db(self, user_id: str, token_data: OAuthTokenData):
        """
        Save OAuth token data to the database.
        It also updates the db_token and scopes attribute.

        Args:
            user_id (str): The unique identifier of the user.
            token_data (OAuthTokenData): The OAuth token data containing access_token,
                refresh_token (optional), and expires_in.

        Returns:
            None
        """
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_data.get("expires_in", 0))
        sqldb.set_oauth(
            user_id=user_id,
            community=self.community_type,
            access_token=token_data["access_token"],  # pyright: ignore[reportTypedDictNotRequiredAccess]
            refresh_token=token_data.get("refresh_token"),
            expires_at=expires_at,
        )
        # 更新快取的 token
        self.db_token = sqldb.get_oauth(user_id, self.community_type)
        self.scopes = token_data.get("scope")

    def to_oauth_data(self) -> OAuthTokenData:
        """將資料庫中的 token 轉換為 OAuthTokenData 格式"""
        if not self.db_token:
            raise Exception("No token loaded from database.")

        return {
            "access_token": self.db_token.access_token,
            "refresh_token": self.db_token.refresh_token,
            "token_type": "Bearer",
            "expires_in": int((self.db_token.expires_at - datetime.now(timezone.utc)).total_seconds()),
        }
