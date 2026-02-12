from authlib.integrations.starlette_client import OAuth
from typing import TypedDict, cast


class OAuthToken(TypedDict, total=False):
    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str | None
    scope: str | None


oauth = OAuth()

oauth.register(
    name="discord",
    client_id="DISCORD_CLIENT_ID",
    client_secret="DISCORD_CLIENT_SECRET",
    access_token_url="https://discord.com/api/oauth2/token",
    authorize_url="https://discord.com/api/oauth2/authorize",
    client_kwargs={"scope": "identify email"},
)


async def test(request):
    token = cast(OAuthToken, await oauth.discord.authorize_access_token(request))
