import uvicorn
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.requests import Request
from google_auth_oauthlib.flow import Flow

from starlib.dataExtractor.oauth import DiscordOauth2, TwitchOauth2, GoogleOauth2
from starlib import Jsondb
from starlib.types import CommunityType

discord_oauth_settings = Jsondb.get_token("discord_oauth")
twitch_oauth_settings = Jsondb.get_token("twitch_oauth")
google_oauth_settings = Jsondb.get_token("google_oauth")

app = FastAPI()

@app.get('/')
@app.head('/')
def main(request:Request):
    return HTMLResponse('這是一個目前沒有內容的主頁')

@app.get("/oauth/discord")
async def oauth_discord(request:Request):
    params = dict(request.query_params)
    code = params.get('code')
    if not code:
        return HTMLResponse(f'授權失敗：{params}', 400)

    auth = DiscordOauth2(**discord_oauth_settings)
    auth.exchange_code(code)
    auth.save_token(auth.user_id)

    connections = auth.get_connections()
    for connection in connections:
        if connection.type == 'twitch':
            print(f"{connection.name}({connection.id})")
            # sclient.sqldb.merge(CloudUser(discord_id=auth.user_id, twitch_id=connection.id))
    return HTMLResponse(f'授權已完成，您現在可以關閉此頁面<br><br>Discord ID：{auth.user_id}')

@app.get('/oauth/twitch')
async def oauth_twitch(request:Request):
    params = dict(request.query_params)
    code = params.get('code')
    if not code:
        return HTMLResponse(f'授權失敗：{params}', 400)
    
    auth = TwitchOauth2(**twitch_oauth_settings)
    auth.exchange_code(code)
    auth.save_token(auth.user_id)
    #sclient.sqldb.merge(TwitchBotJoinChannel(twitch_id=auth.user_id))
    return HTMLResponse(f'授權已完成，您現在可以關閉此頁面<br>別忘了在聊天室輸入 /mod xingyu1016<br><br>Twitch ID：{auth.user_id}')

@app.get('/oauth/google')
async def oauth_google(request:Request):
    params = dict(request.query_params)
    code = params.get('code')
    if not code:
        return HTMLResponse(f'授權失敗：{params}', 400)
    
    SCOPES = ["https://www.googleapis.com/auth/userinfo.profile", "https://www.googleapis.com/auth/userinfo.email", "openid", "https://www.googleapis.com/auth/youtube"]
    auth = GoogleOauth2(scopes=SCOPES, redirect_uri=google_oauth_settings.get('redirect_uri'))

    flow = Flow.from_client_secrets_file(
        'database/google_client_credentials.json',
        scopes=auth.scopes,
        redirect_uri=auth.redirect_uri
    )
    flow.fetch_token(code=code)
    
    auth.set_creds(flow.credentials)
    auth.save_token(auth.user_id)
    return HTMLResponse(f'授權已完成，您現在可以關閉此頁面<br><br>Google ID：{auth.user_id}')


uvicorn.run(app, host="127.0.0.1", port=14000)