# oauth_lib.py
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import TypedDict

from authlib.integrations.httpx_client import AsyncOAuth2Client
from ..models.postgresql import OAuthClient, OAuthToken, OAuthToken
from ..types import CommunityType
from ..database import sqldb


class OAuthTokenDict(TypedDict, total=False):
    access_token: str
    refresh_token: str | None
    token_type: str
    expires_in: int
    scope: str | None


class OAuth2Base(ABC):
    client: AsyncOAuth2Client

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str, scopes: list[str] | None = None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scopes = scopes
        self.db_token: OAuthToken | None = None
        self._credential_id: int | None = None
        self._client: AsyncOAuth2Client | None = None

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
        if self._client is None:
            self._client = AsyncOAuth2Client(
                client_id=self.client_id,
                client_secret=self.client_secret,
                redirect_uri=self.redirect_uri,
                scope=self.scopes,
            )
            self._client.headers["Client-Id"] = self.client_id
        return self._client

    # ====== Authorization URL ======
    def get_authorization_url(self) -> str:
        client = self.oauth_client
        uri, _ = client.create_authorization_url(self.auth_url)
        return uri

    # ====== Basic functions ======
    async def exchange_code(self, code: str, auto_load_token: bool = True) -> OAuthTokenDict:
        """
        Exchange an authorization code for an OAuth token.
        By default, it automatically loads the received token into
        the current instance, but it does NOT save the token to the database - you must
        call `save_token_to_db` separately to persist the token.

        Args:
            code (str): The authorization code received from the OAuth provider
                after user authorization.
            auto_load_token (bool): Whether to automatically load the received token
                into the current instance. Default is True.
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
            client_id=self.client_id,
            client_secret=self.client_secret,
        )

        if token.get("message"):
            raise Exception(f"OAuth Token Exchange Error: {token}")

        if auto_load_token:
            self.db_token = self.to_db_token(token)
            self.db_token.client_credential_id = self._credential_id
            self.scopes = self.db_token.scope

        return token

    async def refresh(self, refresh_token: str) -> OAuthTokenDict:
        client = self.oauth_client
        token = await client.refresh_token(
            url=self.token_url,
            refresh_token=refresh_token,
        )
        return token

    def has_scope(self, scope: str) -> bool:
        if not self.scopes:
            return False
        return scope in self.scopes

    # ====== Signed GET/POST ======
    async def api_get(self, token: OAuthTokenDict, path: str, params: dict | None = None) -> dict:
        client = self.oauth_client
        client.token = token
        resp = await client.get(f"{self.api_url}{path}", params=params)
        resp.raise_for_status()
        return resp.json()

    # ====== Token DB Integration ======
    @classmethod
    def create_from_db(cls, oauth_client: OAuthClient, scopes: str | None = None):
        instance = cls(client_id=oauth_client.client_id, client_secret=oauth_client.client_secret, redirect_uri=oauth_client.redirect_uri, scopes=scopes)
        instance._credential_id = oauth_client.credential_id
        return instance

    def load_token_from_db(self, user_id: str) -> OAuthToken:
        if not self._credential_id:
            raise Exception("OAuth client not initialized from DB.")
        token = sqldb.get_oauth_token(user_id, self._credential_id)
        if not token:
            raise Exception("OAuth token not found.")
        self.db_token = token
        return token

    def save_token_to_db(self, user_id: str, token_data: OAuthTokenDict | None = None):
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
        if not self._credential_id:
            raise Exception("OAuth client not initialized from DB.")

        if token_data is not None:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_data.get("expires_in", 0))
            token = OAuthToken(
                user_id=user_id,
                client_credential_id=self._credential_id,
                access_token=token_data["access_token"],  # pyright: ignore[reportTypedDictNotRequiredAccess]
                refresh_token=token_data.get("refresh_token"),
                scope=token_data.get("scope"),
                expires_at=expires_at,
            )
            sqldb.merge(token)
        elif self.db_token is not None:
            self.db_token.user_id = user_id
            sqldb.merge(self.db_token)
        else:
            raise Exception("No token data to save.")

        # 更新快取的 token
        self.db_token = sqldb.get_oauth_token(user_id, self._credential_id)
        self.scopes = self.db_token.scope

    def to_oauth_dict(self) -> OAuthTokenDict:
        """將資料庫中的 token 轉換為 OAuthTokenDict 格式"""
        if not self.db_token:
            raise Exception("No token loaded from database.")

        return {
            "access_token": self.db_token.access_token,
            "refresh_token": self.db_token.refresh_token,
            "token_type": "Bearer",
            "expires_in": int((self.db_token.expires_at - datetime.now(timezone.utc)).total_seconds()),
            "scope": " ".join(self.db_token.scope),
        }

    def to_db_token(self, token_data: OAuthTokenDict) -> OAuthToken:
        """將 OAuthTokenDict 轉換為資料庫中的 OAuthToken 格式"""
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_data.get("expires_in", 0))
        scope = token_data.get("scope", [])
        if isinstance(scope, str):
            scope = scope.split(" ")

        return OAuthToken(
            user_id=token_data.get("user_id", ""),
            credential_id=self._credential_id or 0,
            access_token=token_data["access_token"],  # pyright: ignore[reportTypedDictNotRequiredAccess]
            refresh_token=token_data.get("refresh_token"),
            scope=scope,
            expires_at=expires_at,
        )
