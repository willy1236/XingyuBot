import asyncio
import secrets
from datetime import datetime, timedelta

import feedparser
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, status
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.requests import Request
from fastapi.responses import (HTMLResponse, JSONResponse, PlainTextResponse,
                               RedirectResponse, StreamingResponse)
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (ApiClient, Configuration, MessagingApi,
                                  ReplyMessageRequest, TextMessage)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.webhooks.models.message_event import MessageEvent

from starlib import Jsondb, sclient, web_log, BaseThread
from starlib.dataExtractor import DiscordOauth, TwitchOauth
from starlib.models.mysql import CloudUser, TwitchBotJoinChannel
from starlib.models.push import YoutubePush

discord_oauth_settings = Jsondb.get_token("discord_oauth")
twitch_oauth_settings = Jsondb.get_token("twitch_chatbot")
linebot_token = Jsondb.get_token("line_bot")
docs_account = Jsondb.get_token("docs_account")

configuration = Configuration(access_token=linebot_token.get("token"))
handler = WebhookHandler(linebot_token.get("secret"))

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

security = HTTPBasic()
def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, docs_account["account"])
    correct_password = secrets.compare_digest(credentials.password, docs_account["password"])
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

@app.get('/')
def main(request:Request):
    web_log.debug(f'{request.client.host} - {request.method} - {request.url.path}')
    if request.query_params:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return HTMLResponse('OK')

@app.route('/keep_alive',methods=['GET'])
def keep_alive(request:Request):
    return HTMLResponse(content='Bot is aLive!')

# print("[Warning] Server Received & Refused!")
# print("[Warning] Error:", e)
    
async def get_yt_push(content):
    feed = feedparser.parse(content)
    if not feed["entries"][0]:
        return
    embed = YoutubePush(**feed["entries"][0]).embed()
    
    if sclient.bot:
        msg = sclient.bot.send_message(embed=embed)
        if not msg:
            print('Channel not found. Message sent failed.')
    else:
        print('Bot not found.')

@app.get('/youtube_push')
def youtube_push_get(request:Request):
    params = dict(request.query_params)
    if 'hub.challenge' in params:
        return HTMLResponse(content=params['hub.challenge'])
    else:
        return HTMLResponse('OK')

@app.post('/youtube_push')
async def youtube_push_post(request:Request,background_task: BackgroundTasks):
    body = await request.body()
    body = body.decode('UTF-8')
    background_task.add_task(get_yt_push,body)
    return HTMLResponse('OK')

@app.get('/oauth/discord')
async def oauth_discord(request:Request):
    params = dict(request.query_params)
    code = params.get('code')
    if not code:
        return HTMLResponse(f'授權失敗：{params}', 400)

    auth = DiscordOauth(discord_oauth_settings)
    auth.exchange_code(code)
    
    connections = auth.get_connections()
    for connection in connections:
        if connection.type == 'twitch':
            print(f"{connection.name}({connection.id})")
            sclient.sqldb.merge(CloudUser(discord_id=auth.user_id, twitch_id=connection.id))

    return HTMLResponse(f'授權已完成，您現在可以關閉此頁面<br><br>Discord ID：{auth.user_id}')

@app.get('/oauth/twitch')
async def oauth_twitch(request:Request):
    params = dict(request.query_params)
    code = params.get('code')
    if not code:
        return HTMLResponse(f'授權失敗：{params}', 400)
    
    auth = TwitchOauth(twitch_oauth_settings)
    auth.exchange_code(code)
    sclient.sqldb.merge(TwitchBotJoinChannel(twitch_id=auth.user_id))
    return HTMLResponse(f'授權已完成，您現在可以關閉此頁面<br><br>Twitch ID：{auth.user_id}')

@app.post("/linebotcallback")
async def linebot_callback(request:Request):
    signature = request.headers.get('X-Line-Signature')

    # get request body as text
    body = await request.body()
    body = body.decode('UTF-8')
    web_log.info("Request body: " + body)

    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        web_log.info("Invalid signature. Please check your channel access token/channel secret.")
        raise HTTPException(status_code=400, detail="Invalid signature")

    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event:MessageEvent):
    print(type(event))
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=event.message.text)]
            )
        )

@app.get("/to/discordauth")
async def to_discordauth(request:Request):
    return RedirectResponse(url=f"https://discord.com/api/oauth2/authorize?client_id={discord_oauth_settings['id']}&redirect_uri={discord_oauth_settings['redirect_uri']}&response_type=code&scope=identify%20connections")

@app.get("/to/twitchauth")
async def to_twitchauth(request:Request):
    return RedirectResponse(url=f"https://id.twitch.tv/oauth2/authorize?client_id={twitch_oauth_settings['id']}&redirect_uri={twitch_oauth_settings['redirect_uri']}&response_type=code&scope=chat:read+channel:read:subscriptions+moderation:read+channel:read:redemptions+channel:manage:redemptions+channel:manage:raids+channel:read:vips+channel:bot+moderator:read:suspicious_users+channel:manage:polls+channel:manage:predictions&force_verify=true")

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
        super().__init__(name='WebsiteThread')

    def run(self):
        import uvicorn
        host = Jsondb.config.get("webip", "127.0.0.1")
        uvicorn.run(app, host=host, port=14000)
        #os.system('uvicorn bot_website:app --port 14000')

if __name__ == '__main__':
    #os.system('uvicorn bot_website:app --reload')
    # server = ltThread()
    # server.start()
    web = WebsiteThread()
    web.start()