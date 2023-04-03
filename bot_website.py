import os
from fastapi import FastAPI
from fastapi.requests import Request
from fastapi.responses import HTMLResponse

app = FastAPI()

@app.route('/')
def main(request:Request):
    r = HTMLResponse(
        content='test'
    )
    return r

@app.route('/keep_alive')
def keep_alive(request:Request):
    r = HTMLResponse(
        content='Bot is aLive!'
    )
    return r

@app.route('/twitch_eventsub',methods=['POST'])
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
    
@app.route('/youtube_push',methods=['POST'])
def youtube_push(request:Request):
     print(request)
     return 200
     
    
@app.get('/book/{book_id}')
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
    run()