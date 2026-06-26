# google_oauth.py
import logging

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from starlib.database import PlatformType

from .models import GoogleUser
from .oauth_lib import OAuth2Base

log = logging.getLogger(__name__)


class GoogleOAuth(OAuth2Base):
    auth_url = "https://accounts.google.com/o/oauth2/auth"
    token_url = "https://oauth2.googleapis.com/token"
    api_url = "https://www.googleapis.com/oauth2/v1"
    platform_type = PlatformType.Google

    def to_google_creds(self) -> Credentials:
        if not self.db_token:
            raise Exception("No token loaded from database.")
        return Credentials(
            token=self.db_token.access_token,
            refresh_token=self.db_token.refresh_token,
            expiry=self.db_token.expires_at.replace(tzinfo=None),
        )

    def build_service(self, service="people", version="v1"):
        creds = self.to_google_creds()
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return build(service, version, credentials=creds)

    async def get_me(self) -> GoogleUser:
        data = await self.api_get("/userinfo")
        return GoogleUser(**data)
