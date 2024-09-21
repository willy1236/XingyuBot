import asyncio
from datetime import datetime, timedelta

import feedparser
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.requests import Request
from fastapi.responses import (HTMLResponse, JSONResponse, PlainTextResponse,
                               StreamingResponse)
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (ApiClient, Configuration, MessagingApi,
                                  ReplyMessageRequest, TextMessage)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.webhooks.models.message_event import MessageEvent

from starlib import Jsondb, sclient, web_log
from starlib.dataExtractor import DiscordOauth, TwitchOauth
from starlib.models.mysql import CloudUser, TwitchBotJoinChannel
from starlib.models.push import YoutubePush

from .tunnel_threads import BaseThread

app = FastAPI()

discord_oauth_settings = Jsondb.get_token("discord_oauth")
twitch_oauth_settings = Jsondb.get_token("twitch_chatbot")
linebot_token = Jsondb.get_token("line_bot")

configuration = Configuration(access_token=linebot_token.get("token"))
handler = WebhookHandler(linebot_token.get("secret"))

@app.route('/')
def main(request:Request):
    web_log.debug(f'{request.client.host} - {request.method} - {request.url.path}')
    return HTMLResponse('test')

@app.route('/keep_alive',methods=['GET'])
def keep_alive(request:Request):
    return HTMLResponse(content='Bot is aLive!')

# @app.post('/twitch_eventsub',response_class=PlainTextResponse)
# def twitch_eventsub(request:Request):
#     try:
#         if request.method == "POST":
#             data = Request.json()
#             challenge = data['challenge']
#             print('status:',data['subscription']['status'])

#             r = HTMLResponse(
#                 content = challenge,
#                 media_type = 'text/plain',
#                 status_code = 200
#             )
#             return r
#         else:
#             print("[Warning] Server Received & Refused!")
#             return "Refused", 400

#     except Exception as e:
#         print("[Warning] Error:", e)
#         return "Server error", 400
    
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

@app.route('/discord',methods=['GET'])
async def discord_oauth(request:Request):
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

@app.route('/twitchauth',methods=['GET'])
async def twitch_oauth(request:Request):
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