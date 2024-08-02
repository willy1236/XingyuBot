import os
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

from fastapi import BackgroundTasks, FastAPI
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
import httpx

from starlib import Jsondb, log, sclient
from starlib.dataExtractor import DiscordOauth, TwitchOauth
from starlib.models.push import YoutubePush

app = FastAPI()

discord_oauth_settings = Jsondb.get_token("discord_oauth")
twitch_oauth_settings = Jsondb.get_token("twitch_chatbot")

@app.route('/')
def main(request:Request):
    return HTMLResponse('test')

@app.route('/keep_alive',methods=['GET'])
def keep_alive(request:Request):
    r = HTMLResponse(content='Bot is aLive!')
    return r

@app.post('/twitch_eventsub',response_class=PlainTextResponse)
def twitch_eventsub(request:Request):
    try:
        if request.method == "POST":
            data = Request.json()
            challenge = data['challenge']
            print('status:',data['subscription']['status'])

            r = HTMLResponse(
                content = challenge,
                media_type = 'text/plain',
                status_code = 200
            )
            return r
        else:
            print("[Warning] Server Received & Refused!")
            return "Refused", 400

    except Exception as e:
        print("[Warning] Error:", e)
        return "Server error", 400
    
async def get_yt_push(content):
    # 解析XML文件
    # tree = ET.parse(content)
    # root = tree.getroot()
    print(content)
    root = ET.fromstring(content)

    # 创建一个空字典来存储结果
    result = {}

    # 解析entry元素並存入字典中
    entry = root.find('{http://www.w3.org/2005/Atom}entry')
    result['id'] = entry.find('{http://www.w3.org/2005/Atom}id').text
    result['videoId'] = entry.find('{http://www.youtube.com/xml/schemas/2015}videoId').text
    result['channelId'] = entry.find('{http://www.youtube.com/xml/schemas/2015}channelId').text
    result['title'] = entry.find('{http://www.w3.org/2005/Atom}title').text
    result['link'] = entry.find('{http://www.w3.org/2005/Atom}link').attrib['href']
    result['author_name'] = entry.find('{http://www.w3.org/2005/Atom}author/{http://www.w3.org/2005/Atom}name').text
    result['author_uri'] = entry.find('{http://www.w3.org/2005/Atom}author/{http://www.w3.org/2005/Atom}uri').text
    result['published'] = entry.find('{http://www.w3.org/2005/Atom}published').text
    result['updated'] = entry.find('{http://www.w3.org/2005/Atom}updated').text

    # 輸出結果
    print(result)
    embed = YoutubePush(result).embed()
    if sclient.bot:
        channel = sclient.bot.get_channel(566533708371329026)
        if channel:
            await channel.send(embed=embed)
        else:
            print('Channel not found.')
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
    print(body)
    background_task.add_task(get_yt_push,body)
    return HTMLResponse('OK')

@app.route('/discord',methods=['GET'])
async def discord_oauth(request:Request):
    params = dict(request.query_params)
    auth = DiscordOauth(discord_oauth_settings)
    auth.exchange_code(params['code'])
    
    connections = auth.get_connections()
    for connection in connections:
        if connection.type == 'twitch':
            print(f"{connection.name}({connection.id})")
            sclient.sqldb.add_userdata_value(auth.user_id, "user_data", "twitch_id", connection.id)

    return HTMLResponse(f'授權已完成，您現在可以關閉此頁面<br><br>Discord ID：{auth.user_id}')

@app.route('/twitchauth',methods=['GET'])
async def twitch_oauth(request:Request):
    params = dict(request.query_params)
    auth = TwitchOauth(twitch_oauth_settings)
    auth.exchange_code(params['code'])
    return HTMLResponse(f'授權已完成，您現在可以關閉此頁面<br><br>Twitch ID：{auth.user_id}')

@app.api_route("/twitch_bot/callback", methods=["GET", "POST"])
async def twitch_bot_callback(request: Request):
    async with httpx.AsyncClient() as client:
        proxy_url = f"http://127.0.0.1:14001{request.url.path}"
        proxy_response = await client.request(
            method=request.method,
            url=proxy_url,
            headers=request.headers.raw,
            content=await request.body()
        )
        return StreamingResponse(proxy_response.aiter_raw(), status_code=proxy_response.status_code)

# @app.get('/book/{book_id}',response_class=JSONResponse)
# def get_book_by_id(book_id: int):
#     return {
#         'book_id': book_id
#     }

# @app.get("/items/{id}", response_class=HTMLResponse)
# async def read_item(request: Request, id: str):
#     html_file = open().read()
#     return html_file


class ltThread(threading.Thread):
    def __init__(self):
        super().__init__(name='ltThread')
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        reconnection_times = 0
        while not self._stop_event.is_set():
            log.info("Starting ltThread")
            os.system('lt --port 14000 --subdomain starbot --max-sockets 10 --local-host 127.0.0.1 --max-https-sockets 86395')
            #cmd = [ "cmd","/c",'lt', '--port', '14000', '--subdomain', 'willy1236', '--max-sockets', '10', '--local-host', '127.0.0.1', '--max-https-sockets', '86395']
            #cmd = ["cmd","/c","echo", "Hello, World!"]
            #self.process = psutil.Popen(cmd)
            #self.process.wait()
            log.info("Finished ltThread")
            time.sleep(5)
            reconnection_times += 1
            if reconnection_times >= 5:
                self._stop_event.set()

        print("ltThread stopped")

class ServeoThread(threading.Thread):
    def __init__(self):
        super().__init__(name='ServeoThread')
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        reconnection_times = 0
        while not self._stop_event.is_set():
            log.info("Starting ServeoThread")
            result = subprocess.run(" ", shell=True, capture_output=True, text=True)
            print(result.stdout)
            time.sleep(60)
            reconnection_times += 1
            if reconnection_times >= 5:
                self._stop_event.set()
class LoopholeThread(threading.Thread):
    def __init__(self):
        super().__init__(name='LoopholeThread')
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        reconnection_times = 0
        while not self._stop_event.is_set():
            log.info("Starting LoopholeThread")
            result = subprocess.run("loophole http 14000 127.0.0.1 --hostname star1016", shell=True, capture_output=True, text=True)
            print(result.stdout)
            time.sleep(30)
            reconnection_times += 1
            if reconnection_times >= 5:
                self._stop_event.set()

class WebsiteThread(threading.Thread):
    def __init__(self):
        super().__init__(name='WebsiteThread')
        self._stop_event = threading.Event()

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