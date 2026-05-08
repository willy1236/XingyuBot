from fastapi import FastAPI
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import Configuration

from v2_starDiscord.bot import DiscordBot
from v2_starlib.database import APIType, SQLRepository
from v2_starlib.providers.social.platforms import GoogleAPI

from .main import SentryExceptionMiddleware, router


def setup_star_server(app: FastAPI, bot: DiscordBot, sqldb: SQLRepository, google_api: GoogleAPI):
    # 這裡才初始化 OAuth 等 Web 專用變數
    app.state.bot = bot
    app.state.sqldb = sqldb
    app.state.google_api = google_api
    app.state.discord_oauth_client = sqldb.get_oauth_client(APIType.Discord, 4)
    app.state.twitch_oauth_client = sqldb.get_oauth_client(APIType.Twitch, 3)
    app.state.google_oauth_settings = sqldb.get_oauth_client(APIType.Google, 3)
    app.state.docs_account = sqldb.get_identifier_secret(APIType.DocAccount)
    app.state.configuration = Configuration(access_token=sqldb.get_access_token(APIType.Line).access_token)
    app.state.handler = WebhookHandler(sqldb.get_identifier_secret(APIType.Line).client_secret)

    app.add_middleware(SentryExceptionMiddleware)

    # 註冊路由
    app.include_router(router)
