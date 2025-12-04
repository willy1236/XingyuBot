# discord_oauth.py
from .oauth_lib import OAuth2Base
from ..types import CommunityType
from ..models import DiscordUser, UserConnection


class DiscordOAuth(OAuth2Base):
    auth_url = "https://discord.com/api/oauth2/authorize"
    token_url = "https://discord.com/api/oauth2/token"
    api_url = "https://discord.com/api/v10"
    community_type = CommunityType.Discord

    async def get_me(self):
        data = await self.api_get(self.to_oauth_dict(), "/users/@me")
        return DiscordUser(**data)

    async def get_connections(self):
        data = await self.api_get(self.to_oauth_dict(), "/users/@me/connections")
        return [UserConnection(**i) for i in data]
