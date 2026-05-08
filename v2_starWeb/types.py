from fastapi import Request
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import Configuration

from v2_starDiscord.bot import DiscordBot
from v2_starlib.database import IdentifierSecret, OAuthClient, SQLRepository


class StarState:
    """明確標註 state 裡面有哪些東西"""

    bot: DiscordBot
    sqldb: SQLRepository
    discord_oauth_client: OAuthClient
    twitch_oauth_client: OAuthClient
    google_oauth_settings: OAuthClient
    docs_account: IdentifierSecret
    configuration: Configuration
    handler: WebhookHandler


class StarRequest(Request):
    """自定義 Request 類別"""

    @property
    def app_state(self) -> StarState:
        return self.app.state  # type: ignore
