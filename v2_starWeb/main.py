import asyncio
import json
import logging
import secrets
from datetime import datetime, timedelta
from pathlib import Path

import feedparser
import uvicorn
from apscheduler.triggers.date import DateTrigger
from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, HTTPException, status
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from jose import jwt
from starlette.middleware.base import BaseHTTPMiddleware

from sentry_bootstrap import capture_exception_safe
from v2_starDiscord.bot import DiscordBot
from v2_starlib import utils
from v2_starlib.base import get_settings
from v2_starlib.database import APIType, ExternalAccount, NotifyCommunityType, PlatformType, SQLRepository, TwitchBotJoinChannel
from v2_starlib.oauth import DiscordOAuth, GoogleOAuth, TwitchOAuth
from v2_starlib.providers.social.push_models import YoutubePushEntry

from .types import StarRequest

SETTINGS = get_settings()
BASE_WWW_URL = SETTINGS.BASE_WWW_URL
BASE_DOMAIN = SETTINGS.BASE_DOMAIN

router = APIRouter(prefix="", tags=["WEB"])
log = logging.getLogger(__name__)

class SentryExceptionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except HTTPException:
            raise
        except Exception as exc:
            capture_exception_safe(
                exc,
                tags={"service": "website", "source": "middleware"},
                extras={"path": request.url.path, "method": request.method},
            )
            log.exception("Unhandled website exception: %s", exc)
            return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


security = HTTPBasic()


def get_current_username(request: StarRequest, credentials: HTTPBasicCredentials = Depends(security)):
    docs_account = request.app_state.docs_account
    correct_username = secrets.compare_digest(credentials.username, docs_account.client_id)
    correct_password = secrets.compare_digest(credentials.password, docs_account.client_secret)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


@router.get("/docs", include_in_schema=False)
async def get_documentation(username: str = Depends(get_current_username)):
    return get_swagger_ui_html(openapi_url="/openapi.json", title="docs")


@router.get("/openapi.json", include_in_schema=False)
async def openapi(username: str = Depends(get_current_username)):
    return get_openapi(title="FastAPI", version="0.1.0", routes=router.routes)


@router.get("/")
@router.head("/")
def main(request: Request):
    log.debug("%s - %s - %s", request.client.host, request.method, request.url.path)
    return HTMLResponse("這是一個目前沒有內容的主頁")


@router.get("/keep_alive")
@router.head("/keep_alive")
def keep_alive(request: Request):
    return HTMLResponse(content="Bot is aLive!")


# print("[Warning] Server Received & Refused!")
# print("[Warning] Error:", e)


async def prase_yt_push(content: str, sqldb: SQLRepository, bot: DiscordBot):
    feed = feedparser.parse(content)
    # with open("test.json", "w", encoding="utf-8") as f:
    # 	json.dump(feed, f, ensure_ascii=False, indent=4)

    for entry in feed["entries"]:
        push_entry = YoutubePushEntry(**entry)
        videos = bot.api.google_api.get_video(push_entry.yt_videoid)
        if not videos:
            log.warning("Video %s not found in YouTube API", push_entry.yt_videoid)
            continue

        video = videos[0]
        cache = sqldb.get_community_cache_with_default(NotifyCommunityType.Youtube, push_entry.yt_channelid)
        ytcache = sqldb.get_yt_cache(push_entry.yt_videoid)
        if push_entry.published > cache.value or (ytcache is not None and video.snippet.liveBroadcastContent == "live"):
            # 透過published的時間來判斷是否為新影片
            log.info("New Youtube push entry %s created at %s", push_entry.yt_videoid, push_entry.published)
            no_mention = False

            if ytcache is not None:
                # 有ytcache：直播開始
                log.info("Removing cached video %s from database", video.id)
                sqldb.remove_yt_cache(video.id)

            elif video.is_live_upcoming_with_time:
                # 如果是即將開始的直播，則添加ytcache
                assert video.liveStreamingDetails.scheduledStartTime is not None, "Scheduled start time should not be None for upcoming live videos"
                log.info("Upcoming live video detected: %s at %s", video.id, video.liveStreamingDetails.scheduledStartTime)
                sqldb.add_yt_cache(video.id, video.liveStreamingDetails.scheduledStartTime)
                no_mention = True
            elif video.liveStreamingDetails and video.liveStreamingDetails.actualEndTime:
                # 已經結束的直播
                log.info("Live video ended: %s at %s", video.id, video.liveStreamingDetails.actualEndTime)
                no_mention = True

            if push_entry.published > cache.value:
                sqldb.set_community_cache(NotifyCommunityType.Youtube, push_entry.yt_channelid, push_entry.published)

            if bot:
                bot.submit(bot.send_notify_communities(video.embed(), NotifyCommunityType.Youtube, push_entry.yt_channelid, no_mention=no_mention))
            else:
                log.warning("Bot not found.")


@router.get("/youtube_push")
def youtube_push_get(request: Request):
    params = dict(request.query_params)
    if "hub.challenge" in params:
        return HTMLResponse(content=params["hub.challenge"])
    else:
        return HTMLResponse("OK")


@router.post("/youtube_push")
async def youtube_push_post(request: StarRequest, background_task: BackgroundTasks):
    body = await request.body()
    body = body.decode("UTF-8")
    background_task.add_task(prase_yt_push, body, request.app_state.sqldb, request.app_state.bot)
    return HTMLResponse("OK")


@router.get("/oauth/discord")
async def oauth_discord(request: StarRequest):
    params = dict(request.query_params)
    code = params.get("code")
    if not code:
        return HTMLResponse(f"授權失敗：{params}", 400)

    # 驗證 state 參數（CSRF 保護）
    # if not OAuth2Base.verify_state(request.cookies.get("oauth_state"), params.get("state")):
    #     return HTMLResponse("授權失敗：state 驗證失敗", 400)

    auth = DiscordOAuth.create_from_db(request.app_state.sqldb, request.app_state.discord_oauth_client)
    await auth.exchange_code(code)
    user = await auth.get_me()
    auth.save_token_to_db(user.id)
    log.info("Discord OAuth: User %s (%s) authorized.", user.username, user.id)
    log.info("Discord OAuth scopes: %s", auth.scopes)

    cuser = request.app_state.sqldb.get_cloud_user_by_discord(user.id)
    if not cuser:
        # 如果資料庫沒有這個用戶，先創建一個新的 CloudUser
        cuser = request.app_state.sqldb.add_cloud_user_by_discord(user.id, user.username)
        log.info("Created new CloudUser for Discord ID %s with username '%s'", user.id, user.username)

    if auth.has_scope("connections"):
        connections = await auth.get_connections()
        for connection in connections:
            if connection.type == "twitch":
                log.info("Discord connection: %s(%s)", connection.name, connection.id)
                request.app_state.sqldb.upsert_external_account(user_id=cuser.id, platform=PlatformType.Twitch, external_id=connection.id, display_name=connection.name)

    if params.get("guild_id"):
        # 機器人授權流程
        response = HTMLResponse(f"授權已完成，您現在可以關閉此頁面<br>感謝您使用星羽機器人！", 200)
        response.delete_cookie("oauth_state")
        return response
    else:
        # 用戶授權流程，產生 JWT 並重定向到儀表板
        response = RedirectResponse(f"{BASE_WWW_URL}/dashboard")

        # 產生 JWT
        payload = {"id": user.id, "username": user.username, "avatar": user.avatar, "exp": datetime.now() + timedelta(days=7)}
        jwt_secret = SETTINGS.JWT_SECRET
        jwt_token = jwt.encode(payload, jwt_secret, algorithm="HS256")

        # 將 JWT 寫入 Cookie
        response.set_cookie(key="jwt", value=jwt_token, httponly=True, secure=True, samesite="lax", max_age=7 * 24 * 60 * 60, domain=f".{BASE_DOMAIN}")
        response.delete_cookie("oauth_state")

        return response


@router.get("/oauth/discordbot")
async def oauth_discordbot(request: StarRequest):
    params = dict(request.query_params)
    code = params.get("code")
    if not code:
        return HTMLResponse(f"授權失敗：{params}", 400)

    return HTMLResponse(f"授權已完成，您現在可以關閉此頁面<br>感謝您使用星羽機器人！", 200)


@router.get("/oauth/twitch")
async def oauth_twitch(request: StarRequest):
    params = dict(request.query_params)
    code = params.get("code")
    if not code:
        return HTMLResponse(f"授權失敗：{params}", 400)

    # 驗證 state 參數（CSRF 保護）
    if not TwitchOAuth.verify_state(request.cookies.get("oauth_state"), params.get("state")):
        return HTMLResponse("授權失敗：state 驗證失敗", 400)

    auth = TwitchOAuth.create_from_db(request.app_state.sqldb, request.app_state.twitch_oauth_client)
    await auth.exchange_code(code)
    user = await auth.get_me()
    auth.save_token_to_db(user.id)
    request.app_state.sqldb.merge(TwitchBotJoinChannel(twitch_id=user.id))
    response = HTMLResponse(f"授權已完成，您現在可以關閉此頁面<br>別忘了在聊天室輸入 /mod xingyu1016<br><br>Twitch ID：{user.id}")
    response.delete_cookie("oauth_state")
    return response


@router.get("/oauth/google")
async def oauth_google(request: StarRequest):
    params = dict(request.query_params)
    code = params.get("code")
    if not code:
        return HTMLResponse(f"授權失敗：{params}", 400)

    # 驗證 state 參數（CSRF 保護）
    if not GoogleOAuth.verify_state(request.cookies.get("oauth_state"), params.get("state")):
        return HTMLResponse("授權失敗：state 驗證失敗", 400)

    auth = GoogleOAuth.create_from_db(request.app_state.sqldb, request.app_state.google_oauth_settings)
    await auth.exchange_code(code)
    auth.save_token_to_db(auth.db_token.user_id)
    response = HTMLResponse(f"授權已完成，您現在可以關閉此頁面<br><br>Google ID：{auth.db_token.user_id}")
    response.delete_cookie("oauth_state")
    return response


@router.get("/to/discordauth")
async def to_discordauth(request: StarRequest):
    auth = DiscordOAuth.create_from_db(request.app_state.discord_oauth_client, scopes=["identify", "connections"])
    url, state = auth.get_authorization_url()
    response = RedirectResponse(url=url)
    response.set_cookie(key="oauth_state", value=state, httponly=True, secure=True, samesite="lax", max_age=600)
    return response


@router.get("/to/twitchauth")
async def to_twitchauth(request: StarRequest):
    twitch_scopes = [
        "chat:read",
        "channel:read:subscriptions",
        "moderation:read",
        "channel:read:redemptions",
        "channel:manage:redemptions",
        "channel:manage:raids",
        "channel:read:vips",
        "channel:bot",
        "moderator:read:suspicious_users",
        "channel:manage:polls",
        "channel:manage:predictions",
    ]
    auth = TwitchOAuth.create_from_db(request.app_state.twitch_oauth_client, scopes=twitch_scopes)
    url, state = auth.get_authorization_url(force_verify="true")
    response = RedirectResponse(url=url)
    response.set_cookie(key="oauth_state", value=state, httponly=True, secure=True, samesite="lax", max_age=600)
    return response


@router.get("/to/discordbot")
async def to_discordbot(request: StarRequest):
    auth = DiscordOAuth.create_from_db(request.app_state.discord_oauth_client, scopes=["identify", "applications.commands.permissions.update", "bot"])
    url, state = auth.get_authorization_url(permissions="8")
    response = RedirectResponse(url=url)
    response.set_cookie(key="oauth_state", value=state, httponly=True, secure=True, samesite="lax", max_age=600)
    return response


@router.get("/to/googleauth")
async def to_googleauth(request: StarRequest):
    # TODO: scopes存放整理
    scopes = [
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/userinfo.email",
        "openid",
        "https://www.googleapis.com/auth/youtube",
    ]
    auth = GoogleOAuth.create_from_db(request.app_state.google_oauth_settings, scopes=scopes)
    url, state = auth.get_authorization_url(access_type="offline")
    response = RedirectResponse(url=url)
    response.set_cookie(key="oauth_state", value=state, httponly=True, secure=True, samesite="lax", max_age=600)
    return response


@router.get("/logout")
async def logout(request: Request):
    response = RedirectResponse(url=BASE_WWW_URL)
    response.delete_cookie("jwt", domain=f".{BASE_DOMAIN}", httponly=True, secure=True, samesite="lax", path="/")
    return response


# 添加一個驗證依賴函數
async def verify_jwt(request: Request):
    jwt_token = request.cookies.get("jwt")
    if not jwt_token:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        jwt_secret = SETTINGS.JWT_SECRET
        payload = jwt.decode(jwt_token, jwt_secret, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="JWT expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid JWT")


@router.get("/discord/data")
async def api_discord(user_data: dict = Depends(verify_jwt)):
    return JSONResponse(content={"status": "ok", "message": "Discord API is working", "user": user_data})


# class WebsiteThread(BaseThread):
#     def __init__(self):
#         super().__init__(name="WebsiteThread")
#         self.server = None
#         self.loop = None

#     def run(self):
#         cert_dir = Path(__file__).parent.parent / "database"
#         certfile = cert_dir / "localhost+2.pem"
#         keyfile = cert_dir / "localhost+2-key.pem"
#         app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
#         setup_star_server(app, None, sqldb)

#         if certfile.exists() and keyfile.exists():
#             config = uvicorn.Config(
#                 app,
#                 host="0.0.0.0",
#                 port=14000,
#                 ssl_certfile=str(certfile),
#                 ssl_keyfile=str(keyfile),
#             )
#         else:
#             config = uvicorn.Config(app, host="0.0.0.0", port=14000)

#         self.server = uvicorn.Server(config)

#         # ⚠ 使用獨立 event loop，不使用 asyncio.run()
#         self.loop = asyncio.new_event_loop()
#         asyncio.set_event_loop(self.loop)

#         try:
#             self.loop.run_until_complete(self.server.serve())
#         except Exception as exc:
#             capture_exception_safe(exc, tags={"service": "website", "source": "website_thread_run"})
#             log.exception("Website thread crashed: %s", exc)
#             raise
#         finally:
#             self.loop.close()

#     def stop(self):
#         if self.server:
#             self.server.should_exit = True


# if __name__ == "__main__":
#     web = WebsiteThread()
#     web.start()
