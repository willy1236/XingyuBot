import asyncio
import json
import secrets
from datetime import datetime, timedelta

import feedparser
from apscheduler.triggers.date import DateTrigger
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, status
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from google_auth_oauthlib.flow import Flow
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import ApiClient, Configuration, MessagingApi, ReplyMessageRequest, TextMessage
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.webhooks.models.message_event import MessageEvent

from starlib import BaseThread, Jsondb, sclient, sqldb, web_log
from starlib.dataExtractor import DiscordOauth2, GoogleOauth2, TwitchOauth2
from starlib.instance import yt_api
from starlib.models import CloudUser, TwitchBotJoinChannel, YoutubePushEntry
from starlib.types import APIType, NotifyCommunityType

discord_oauth_settings = sqldb.get_bot_token(APIType.Discord)
twitch_oauth_settings = sqldb.get_bot_token(APIType.Twitch)
google_oauth_settings = sqldb.get_bot_token(APIType.Google, 3)
# linebot_token = sqldb.get_bot_token(APIType.Line)
docs_account = sqldb.get_bot_token(APIType.DocAccount)

# configuration = Configuration(access_token=linebot_token.access_token)
# handler = WebhookHandler(linebot_token.client_secret)

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

security = HTTPBasic()
def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, docs_account.client_id)
    correct_password = secrets.compare_digest(credentials.password, docs_account.client_secret)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

@app.get("/docs", include_in_schema=False)
async def get_documentation(username: str = Depends(get_current_username)):
    return get_swagger_ui_html(openapi_url="/openapi.json", title="docs")

@app.get("/openapi.json", include_in_schema=False)
async def openapi(username: str = Depends(get_current_username)):
    return get_openapi(title="FastAPI", version="0.1.0", routes=app.routes)

@app.get("/")
@app.head("/")
def main(request:Request):
    web_log.debug(f"{request.client.host} - {request.method} - {request.url.path}")
    # if not request.query_params or dict(request.query_params).get('code') != "200":
    #     raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return HTMLResponse("這是一個目前沒有內容的主頁")

@app.route("/keep_alive", methods=["GET"])
def keep_alive(request:Request):
    return HTMLResponse(content="Bot is aLive!")

# print("[Warning] Server Received & Refused!")
# print("[Warning] Error:", e)

async def prase_yt_push(content: str):
    feed = feedparser.parse(content)
    # with open("test.json", "w", encoding="utf-8") as f:
    # 	json.dump(feed, f, ensure_ascii=False, indent=4)

    for entry in feed["entries"]:
        push_entry = YoutubePushEntry(**entry)
        video = yt_api.get_video(push_entry.yt_videoid)[0]

        cache = sqldb.get_community_cache_with_default(NotifyCommunityType.Youtube, push_entry.yt_channelid)
        ytcache = sqldb.get_yt_cache(push_entry.yt_videoid)
        if push_entry.published > cache.value or (ytcache is not None and video.snippet.liveBroadcastContent == "live"):
            # 透過published的時間來判斷是否為新影片
            web_log.info(f"New Youtube push entry {push_entry.yt_videoid}")
            no_mention = False

            if ytcache is not None:
                # 有ytcache：直播開始
                web_log.info(f"Removing cached video {video.id} from database")
                sqldb.remove_yt_cache(video.id)

            elif video.is_live_upcoming_with_time:
                # 如果是即將開始的直播，則添加ytcache
                assert video.liveStreamingDetails.scheduledStartTime is not None, "Scheduled start time should not be None for upcoming live videos"
                web_log.info(f"Upcoming live video detected: {video.id} at {video.liveStreamingDetails.scheduledStartTime}")
                sqldb.add_yt_cache(video.id, video.liveStreamingDetails.scheduledStartTime)
                no_mention = True

            if push_entry.published > cache.value:
                sqldb.set_community_cache(NotifyCommunityType.Youtube, push_entry.yt_channelid, push_entry.published)

            if sclient.bot:
                asyncio.run_coroutine_threadsafe(
                    sclient.bot.send_notify_communities(video.embed(), NotifyCommunityType.Youtube, push_entry.yt_channelid, no_mention=no_mention),
                    sclient.bot.loop,
                )
            else:
                web_log.warning("Bot not found.")


@app.get("/youtube_push")
def youtube_push_get(request: Request):
    params = dict(request.query_params)
    if "hub.challenge" in params:
        return HTMLResponse(content=params["hub.challenge"])
    else:
        return HTMLResponse("OK")


@app.post("/youtube_push")
async def youtube_push_post(request: Request, background_task: BackgroundTasks):
    body = await request.body()
    body = body.decode("UTF-8")
    background_task.add_task(prase_yt_push, body)
    return HTMLResponse("OK")


@app.get("/oauth/discord")
async def oauth_discord(request: Request):
    params = dict(request.query_params)
    code = params.get("code")
    if not code:
        return HTMLResponse(f"授權失敗：{params}", 400)

    auth = DiscordOauth2.from_bot_token(discord_oauth_settings)
    auth.exchange_code(code)
    auth.save_token(auth.user_id)

    connections = auth.get_connections()
    for connection in connections:
        if connection.type == "twitch":
            print(f"{connection.name}({connection.id})")
            sclient.sqldb.merge(CloudUser(discord_id=auth.user_id, twitch_id=connection.id))

    return HTMLResponse(f"授權已完成，您現在可以關閉此頁面<br><br>Discord ID：{auth.user_id}")


@app.get("/oauth/discordbot")
async def oauth_discordbot(request: Request):
    params = dict(request.query_params)
    code = params.get("code")
    if not code:
        return HTMLResponse(f"授權失敗：{params}", 400)

    return HTMLResponse(f"授權已完成，您現在可以關閉此頁面<br>感謝您使用星羽機器人！", 200)


@app.get("/oauth/twitch")
async def oauth_twitch(request: Request):
    params = dict(request.query_params)
    code = params.get("code")
    if not code:
        return HTMLResponse(f"授權失敗：{params}", 400)

    auth = TwitchOauth2.from_bot_token(twitch_oauth_settings)
    auth.exchange_code(code)
    auth.save_token(auth.user_id)
    sclient.sqldb.merge(TwitchBotJoinChannel(twitch_id=auth.user_id))
    return HTMLResponse(f"授權已完成，您現在可以關閉此頁面<br>別忘了在聊天室輸入 /mod xingyu1016<br><br>Twitch ID：{auth.user_id}")


@app.get("/oauth/google")
async def oauth_google(request: Request):
    params = dict(request.query_params)
    code = params.get("code")
    if not code:
        return HTMLResponse(f"授權失敗：{params}", 400)

    auth = GoogleOauth2.from_bot_token(google_oauth_settings)

    # flow = Flow.from_client_secrets_file(
    #     'database/google_client_credentials.json',
    #     scopes=auth.scopes,
    #     redirect_uri=auth.redirect_uri
    # )
    # flow.fetch_token(code=code)
    auth.exchange_code(code)
    auth.set_creds()
    auth.save_token(auth.user_id)
    return HTMLResponse(f"授權已完成，您現在可以關閉此頁面<br><br>Google ID：{auth.user_id}")


# @app.post("/linebotcallback")
# async def linebot_callback(request:Request):
#     signature = request.headers.get('X-Line-Signature')

#     # get request body as text
#     body = await request.body()
#     body = body.decode('UTF-8')
#     web_log.info("Request body: " + body)

#     # handle webhook body
#     try:
#         handler.handle(body, signature)
#     except InvalidSignatureError:
#         web_log.info("Invalid signature. Please check your channel access token/channel secret.")
#         raise HTTPException(status_code=400, detail="Invalid signature")

#     return 'OK'

# @handler.add(MessageEvent, message=TextMessageContent)
# def handle_message(event:MessageEvent):
#     print(type(event))
#     with ApiClient(configuration) as api_client:
#         line_bot_api = MessagingApi(api_client)
#         line_bot_api.reply_message_with_http_info(
#             ReplyMessageRequest(
#                 reply_token=event.reply_token,
#                 messages=[TextMessage(text=event.message.text)]
#             )
#         )


@app.get("/to/discordauth")
async def to_discordauth(request: Request):
    return RedirectResponse(
        url=f"https://discord.com/api/oauth2/authorize?client_id={discord_oauth_settings.client_id}&redirect_uri={discord_oauth_settings.redirect_uri}&response_type=code&scope=identify%20connections"
    )


@app.get("/to/twitchauth")
async def to_twitchauth(request: Request):
    return RedirectResponse(
        url=f"https://id.twitch.tv/oauth2/authorize?client_id={twitch_oauth_settings.client_id}&redirect_uri={twitch_oauth_settings.redirect_uri}&response_type=code&scope=chat:read+channel:read:subscriptions+moderation:read+channel:read:redemptions+channel:manage:redemptions+channel:manage:raids+channel:read:vips+channel:bot+moderator:read:suspicious_users+channel:manage:polls+channel:manage:predictions&force_verify=true"
    )


@app.get("/to/googleauth")
async def to_googleauth(request: Request):
    # TODO: scopes存放整理
    scopes = [
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/userinfo.email",
        "openid",
        "https://www.googleapis.com/auth/youtube",
    ]
    config = sqldb.get_google_client_config(3)
    flow = Flow.from_client_config(config, scopes=scopes)
    url = flow.authorization_url()[0]
    return RedirectResponse(url=url)


# @app.get('/book/{book_id}',response_class=JSONResponse)
# def get_book_by_id(book_id: int):
#     return {
#         'book_id': book_id
#     }

# @app.get("/items/{id}", response_class=HTMLResponse)
# async def read_item(request: Request, id: str):
#     html_file = open().read()
#     return html_file


class WebsiteThread(BaseThread):
    def __init__(self):
        super().__init__(name="WebsiteThread")

    def run(self):
        import uvicorn

        host = Jsondb.config.get("webip", "127.0.0.1")
        uvicorn.run(app, host=host, port=14000)
        # os.system('uvicorn bot_website:app --port 14000 --reload')


if __name__ == "__main__":
    web = WebsiteThread()
    web.start()
