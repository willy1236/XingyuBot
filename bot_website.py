import os,time
from fastapi import FastAPI,BackgroundTasks
from fastapi.requests import Request
from fastapi.responses import HTMLResponse,JSONResponse,PlainTextResponse
import xml.etree.ElementTree as ET

app = FastAPI()

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
    
def get_yt_push(content):
    tree = ET.parse(content)
    root = tree.getroot()

    result = {}
    result['id'] = root.find('id').text
    result['videoId'] = root.find('yt:videoId', root.nsmap).text
    result['channelId'] = root.find('yt:channelId', root.nsmap).text
    result['title'] = root.find('title').text
    result['link'] = root.find('link').get('href')
    result['author'] = root.find('author/name').text
    result['author_uri'] = root.find('author/uri').text
    result['published'] = root.find('published').text
    result['updated'] = root.find('updated').text

    print(result)

@app.get('/youtube_push')
def youtube_push_get(request:Request):
    params = dict(request.query_params)
    print(params)
    if 'hub.challenge' in params:
        return HTMLResponse(content=params['hub.challenge'])  
    else:
        return HTMLResponse('OK')

@app.post('/youtube_push')
def youtube_push_post(request:Request,background_task: BackgroundTasks):
    background_task.add_task(get_yt_push,request.body)
    return HTMLResponse('OK')

@app.get('/book/{book_id}',response_class=JSONResponse)
def get_book_by_id(book_id: int):
    return {
        'book_id': book_id
    }

@app.get("/items/{id}", response_class=HTMLResponse)
async def read_item(request: Request, id: str):
    html_file = open().read()
    return html_file


def run():
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=14000)

if __name__ == '__main__':
    #os.system('uvicorn bot_website:app --reload')
    from cmds.task import ltThread
    server = ltThread()
    server.start()

    run()