# discord_oauth.py
import logging

from starlib.database import PlatformType

from .models import DiscordUser, UserConnection
from .oauth_lib import OAuth2Base

log = logging.getLogger(__name__)


class DiscordOAuth(OAuth2Base):
    auth_url = "https://discord.com/api/oauth2/authorize"
    token_url = "https://discord.com/api/oauth2/token"
    api_url = "https://discord.com/api/v10"
    revoke_url = "https://discord.com/api/oauth2/token/revoke"
    platform_type = PlatformType.Discord

    async def get_me(self) -> DiscordUser:
        data = await self.api_get("/users/@me")
        return DiscordUser(**data)

    async def get_connections(self) -> list[UserConnection]:
        data = await self.api_get("/users/@me/connections")
        return [UserConnection(**i) for i in data]

    async def revoke_token(self, token: str, token_type_hint: str = "access_token") -> None:
        """向 Discord 撤銷授權。撤銷 access token 或 refresh token 任一個，整份授權都會失效。

        Raises:
            httpx.HTTPStatusError: Discord 回非 2xx。
        """
        resp = await self.oauth_client.revoke_token(self.revoke_url, token=token, token_type_hint=token_type_hint)
        resp.raise_for_status()
