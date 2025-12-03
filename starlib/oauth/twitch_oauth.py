# twitch_oauth.py
from .oauth_lib import OAuth2Base
from ..types import CommunityType


class TwitchOAuth(OAuth2Base):
    auth_url = "https://id.twitch.tv/oauth2/authorize"
    token_url = "https://id.twitch.tv/oauth2/token"
    api_url = "https://api.twitch.tv/helix"
    community_type = CommunityType.Twitch

    async def get_user(self, token):
        params = {"id": token.get("user_id")}
        return await self.api_get(token, "/users", params=params)
