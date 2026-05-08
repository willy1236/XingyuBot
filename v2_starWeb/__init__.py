from fastapi import FastAPI
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import Configuration

from v2_starDiscord.bot import DiscordBot
from v2_starlib.database import APIType, SQLRepository

from .main import router


def setup_star_server(app: FastAPI, bot: DiscordBot, sqldb: SQLRepository):
    # 這裡才初始化 OAuth 等 Web 專用變數
    app.state.bot = bot
    app.state.sqldb = sqldb
    app.state.discord_oauth_client = sqldb.get_oauth_client(APIType.Discord, 4)
    app.state.twitch_oauth_client = sqldb.get_oauth_client(APIType.Twitch, 3)
    app.state.google_oauth_settings = sqldb.get_oauth_client(APIType.Google, 3)
    app.state.docs_account = sqldb.get_identifier_secret(APIType.DocAccount)
    app.state.configuration = Configuration(access_token=sqldb.get_access_token(APIType.Line).access_token)
    app.state.handler = WebhookHandler(sqldb.get_identifier_secret(APIType.Line).client_secret)

    # 註冊路由
    app.include_router(router)
