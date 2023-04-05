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
    # 解析XML文件
    tree = ET.parse(content)
    root = tree.getroot()

    # 创建一个空字典来存储结果
    result = {}

    # 判断是否为已删除条目
    if 'deleted-entry' in root.tag:
        # 获取删除的视频ID和删除的时间并添加到字典中
        result['deleted_videoId'] = root.get('ref').split(':')[-1]
        result['deleted_time'] = root.get('when')

        # 如果有一个<by>元素，获取作者信息并添加到字典中
        by_elem = root.find('at:by', root.nsmap)
        if by_elem is not None:
            result['author'] = by_elem.find('name').text
            result['author_uri'] = by_elem.find('uri').text
    else:
        # 获取视频ID、频道ID和视频标题，并添加到字典中
        video_id_elem = root.find('yt:videoId', root.nsmap)
        result['video_id'] = video_id_elem.text
        channel_id_elem = root.find('yt:channelId', root.nsmap)
        result['channel_id'] = channel_id_elem.text
        title_elem = root.find('title')
        result['title'] = title_elem.text

        # 如果有一个<author>元素，获取作者信息并添加到字典中
        author_elem = root.find('author')
        if author_elem is not None:
            result['author'] = author_elem.find('name').text
            result['author_uri'] = author_elem.find('uri').text

        # 获取发布时间和更新时间，并添加到字典中
        published_elem = root.find('published')
        result['published'] = published_elem.text
        updated_elem = root.find('updated')
        result['updated'] = updated_elem.text

    # 输出结果
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