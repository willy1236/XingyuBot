# google_oauth.py
from .oauth_lib import OAuth2Base
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from ..types import CommunityType


class GoogleOAuth(OAuth2Base):
    auth_url = "https://accounts.google.com/o/oauth2/auth"
    token_url = "https://oauth2.googleapis.com/token"
    api_url = "https://www.googleapis.com/oauth2/v1"
    community_type = CommunityType.Google

    def to_google_creds(self, token):
        return Credentials(
            token=token["access_token"],
            refresh_token=token.get("refresh_token"),
            expiry=token["expires_at"].replace(tzinfo=None),
        )

    def build_service(self, token, service="people", version="v1"):
        creds = self.to_google_creds(token)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return build(service, version, credentials=creds)

    async def get_me(self, token):
        return await self.api_get(token, "/userinfo")
