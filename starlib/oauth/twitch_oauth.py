# twitch_oauth.py
from starlib.database import CommunityType
from starlib.providers.social.models import TwitchUser

from .oauth_lib import OAuth2Base


class TwitchOAuth(OAuth2Base):
    auth_url = "https://id.twitch.tv/oauth2/authorize"
    token_url = "https://id.twitch.tv/oauth2/token"
    api_url = "https://api.twitch.tv/helix"
    community_type = CommunityType.Twitch

    async def get_me(self) -> TwitchUser:
        data = await self.api_get(self.to_oauth_dict(), "/users")
        return TwitchUser(**data["data"][0])
