import asyncio
import hashlib
import hmac
import html
import logging
import secrets
from pathlib import Path

import feedparser
import uvicorn
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, status
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.requests import Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import ApiClient, Configuration, MessagingApi, ReplyMessageRequest, TextMessage
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from sentry_bootstrap import capture_exception_safe
from starlib import BaseThread, sclient, sqldb, utils
from starlib.database import APIType, NotifyCommunityType, TwitchBotJoinChannel
from starlib.identity import MemberUnknown, TwitchMember, lookup_twitch_member
from starlib.instance import google_api
from starlib.oauth import DiscordOAuth, TwitchOAuth
from starlib.providers.social.push_models import YoutubePushEntry
from starlib.settings import get_settings
from starlib.starAgent_line import line_agent
from starServer import dashboard
from starServer.dashboard import config as dashboard_config
from starServer.dashboard.auth import handle_dashboard_oauth

discord_oauth_client = sqldb.get_oauth_client(APIType.Discord, 4)
twitch_oauth_client = sqldb.get_oauth_client(APIType.Twitch, 3)
docs_account = sqldb.get_identifier_secret(APIType.DocAccount)
websub_config = sqldb.get_websub_config(APIType.Google, 4)

configuration = Configuration(access_token=sqldb.get_access_token(APIType.Line).access_token)
parser = WebhookParser(sqldb.get_identifier_secret(APIType.Line).client_secret)

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
log = logging.getLogger(__name__)


@app.middleware("http")
async def sentry_exception_middleware(request: Request, call_next):
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


# 必須在 sentry_exception_middleware 之後：CORS 才會在最外層，500 回應也帶得到 CORS header
dashboard.install(app)

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
    log.debug(f"{request.client.host} - {request.method} - {request.url.path}")
    return HTMLResponse("這是一個目前沒有內容的主頁")

@app.get("/keep_alive")
@app.head("/keep_alive")
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
        videos = google_api.get_video(push_entry.yt_videoid)
        if not videos:
            log.warning(f"Video {push_entry.yt_videoid} not found in YouTube API")
            continue

        video = videos[0]
        # 以 YouTube API 回傳的頻道為準，不信任 feed 自報的頻道 ID
        channel_id = video.snippet.channelId
        ytcache = sqldb.get_yt_cache(push_entry.yt_videoid)
        # 透過published的時間原子地搶佔快取，避免與 RSS 輪詢重複通知同一部影片
        claimed = sqldb.claim_community_cache(NotifyCommunityType.Youtube, channel_id, push_entry.published)
        if claimed or (ytcache is not None and video.snippet.liveBroadcastContent == "live"):
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

            if sclient.bot:
                sclient.bot.submit(
                    sclient.bot.send_notify_communities(video.embed(), NotifyCommunityType.Youtube, channel_id, no_mention=no_mention)
                )
            else:
                log.warning("Bot not found.")


@app.get("/youtube_push")
def youtube_push_get(request: Request):
    params = dict(request.query_params)
    if "hub.challenge" in params:
        return HTMLResponse(content=params["hub.challenge"])
    else:
        return HTMLResponse("OK")


def verify_websub_signature(body: bytes, signature: str | None) -> bool:
    """驗證 WebSub 的 X-Hub-Signature（sha1=<hex>），未設定 secret 時略過驗證"""
    secret = websub_config.hub_secret if websub_config else None
    if not secret:
        log.warning("WebSub hub_secret is not configured, skipping signature verification")
        return True
    if not signature or "=" not in signature:
        return False
    algo, digest = signature.split("=", 1)
    if algo not in ("sha1", "sha256", "sha384", "sha512"):
        return False
    expected = hmac.new(secret.encode(), body, getattr(hashlib, algo)).hexdigest()
    return hmac.compare_digest(expected, digest)


@app.post("/youtube_push")
async def youtube_push_post(request: Request, background_task: BackgroundTasks):
    body = await request.body()
    if not verify_websub_signature(body, request.headers.get("X-Hub-Signature")):
        # 依 WebSub 規範仍回 2xx，避免 hub 重送，但不處理內容
        log.warning("Youtube push signature verification failed")
        return HTMLResponse("OK")
    background_task.add_task(prase_yt_push, body.decode("UTF-8"))
    return HTMLResponse("OK")


@app.get("/oauth/discord")
async def oauth_discord(request: Request):
    # 後台的登入流程（dashboard_oauth cookie 且 state 相符）；回 None 才走下面原本的處理
    response = await handle_dashboard_oauth(request)
    if response is None:
        response = _oauth_discord_fallback(request)
        # 有 dashboard_oauth 但 state 不符時，也一併清掉
        if "dashboard_oauth" in request.cookies:
            response.delete_cookie("dashboard_oauth", httponly=True, secure=True, samesite="lax")
    return response


def _oauth_discord_fallback(request: Request) -> Response:
    params = dict(request.query_params)
    frontend = dashboard_config.frontend_url()

    if params.get("guild_id"):
        # 機器人授權流程。這個流程存下的 token 沒有任何地方讀取，而且會蓋掉後台的 token，所以不換 token、不存
        if not params.get("code"):
            return HTMLResponse(f"授權失敗：{html.escape(params.get('error', '缺少授權碼'))}", 400)
        log.info("Discord OAuth: bot added to guild %s", params["guild_id"])
        response = HTMLResponse("授權已完成，您現在可以關閉此頁面<br>感謝您使用星羽機器人！", 200)
        response.delete_cookie("oauth_state")
        return response

    if params.get("error"):
        return RedirectResponse(url=f"{frontend}/")
    # 例如在 Discord 頁停超過 10 分鐘、dashboard_oauth 已過期：交給後台頁重新走登入
    return RedirectResponse(url=f"{frontend}/dashboard")


@app.get("/oauth/discordbot")
async def oauth_discordbot(request: Request):
    params = dict(request.query_params)
    code = params.get("code")
    if not code:
        return HTMLResponse(f"授權失敗：{html.escape(params.get('error', '缺少授權碼'))}", 400)

    return HTMLResponse("授權已完成，您現在可以關閉此頁面<br>感謝您使用星羽機器人！", 200)


def _twitch_oauth_page(message: str, status_code: int) -> HTMLResponse:
    response = HTMLResponse(message, status_code)
    response.delete_cookie("oauth_state")
    return response


@app.get("/oauth/twitch")
async def oauth_twitch(request: Request):
    params = dict(request.query_params)
    code = params.get("code")
    if not code:
        return _twitch_oauth_page(f"授權失敗：{html.escape(params.get('error', '缺少授權碼'))}", 400)

    if not TwitchOAuth.verify_state(request.cookies.get("oauth_state"), params.get("state")):
        return _twitch_oauth_page("授權失敗：驗證碼不符或已過期，請重新開始授權", 400)

    auth = TwitchOAuth.create_from_db(twitch_oauth_client)
    try:
        await auth.exchange_code(code)
        user = await auth.get_me()
    except Exception as exc:
        capture_exception_safe(exc, tags={"service": "website", "source": "oauth_twitch"})
        log.exception("Twitch OAuth failed: %s", exc)
        return _twitch_oauth_page("授權失敗，請重新開始授權", 400)

    # 只有析域域民才能授權；結果沒有明確答案時不存 token、不登記頻道
    lookup = await lookup_twitch_member(user.id)
    if isinstance(lookup, MemberUnknown):
        log.warning("Twitch OAuth: member lookup unknown for twitch_id=%s", user.id)
        return _twitch_oauth_page("這次授權失敗，請稍後再試", 503)
    if not isinstance(lookup, TwitchMember):
        log.info("Twitch OAuth: twitch_id=%s is not a member, refused", user.id)
        auth_url = html.escape(get_settings().AUTH_PUBLIC_URL)
        return _twitch_oauth_page(f'請先註冊析域帳號並在帳號頁連結這個 Twitch：<a href="{auth_url}">{auth_url}</a>', 403)

    twitch_id = int(user.id)  # 在 try 外：Twitch ID 本來就是數字，格式錯誤不是資料庫寫入失敗
    try:
        auth.save_token_to_db(user.id)
        # 已登記的頻道保留 action_channel_id、point_name，所以沒有才新增，不用 merge
        if sqldb.get(TwitchBotJoinChannel, (twitch_id,)) is None:
            sqldb.add(TwitchBotJoinChannel(twitch_id=twitch_id))
    except Exception as exc:
        capture_exception_safe(exc, tags={"service": "website", "source": "oauth_twitch"})
        log.exception("Twitch OAuth: saving token or channel failed for twitch_id=%s: %s", user.id, exc)
        return _twitch_oauth_page("這次授權失敗，請稍後再試", 503)
    log.info("Twitch OAuth: twitch_id=%s authorized as account %s", user.id, lookup.account_id)

    return _twitch_oauth_page(
        "授權已完成，您現在可以關閉此頁面<br>"
        "請在您的 Twitch 聊天室輸入 <code>/mod xingyu1016</code> 將機器人設為管理員<br>"
        "頻道會在 Twitch 機器人重啟後生效<br>感謝您使用星羽機器人！",
        200,
    )


@app.post("/callback/linebot")
async def callback_linebot(request: Request, background_tasks: BackgroundTasks):
    signature = request.headers.get("X-Line-Signature")

    # get request body as text
    body = await request.body()
    body = body.decode("UTF-8")

    background_tasks.add_task(process_linebot_webhook, body, signature)
    return "OK"


async def process_linebot_webhook(body: str, signature: str):
    """在背景任務中處理 LINE Bot webhook"""
    try:
        for event in parser.parse(body, signature):
            if isinstance(event, MessageEvent) and isinstance(event.message, TextMessageContent):
                await handle_message(event)
    except InvalidSignatureError:
        log.error("Invalid signature in LINE Bot webhook")
    except Exception as e:
        capture_exception_safe(e, tags={"service": "website", "source": "linebot_webhook"})
        log.error("處理 LINE Bot 訊息時發生錯誤", exc_info=e)

async def handle_message(event: MessageEvent):
    url = utils.check_url_format(event.message.text)
    if url:
        report_lines = await asyncio.to_thread(utils.generate_url_report, event.message.text)
        report_text = "\n".join(report_lines)
        try:
            ai_response = await line_agent.run(report_text)
            text = "\n".join([report_text, "", "AI 分析結果:", ai_response.output])
        except Exception as e:
            capture_exception_safe(e, tags={"service": "website", "source": "line_agent"})
            log.error("Error in AI analysis", exc_info=e)
            text = "\n".join([report_text, "", "AI 分析結果: 無法取得分析結果"])

    else:
        text = "請提供一個有效的網址。"

    await asyncio.to_thread(reply_line_message, event.reply_token, text)


def reply_line_message(reply_token: str, text: str):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=text)],
            )
        )


@app.get("/to/twitchauth")
async def to_twitchauth(request: Request):
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
    auth = TwitchOAuth.create_from_db(twitch_oauth_client, scopes=twitch_scopes)
    url, state = auth.get_authorization_url(force_verify="true")
    response = RedirectResponse(url=url)
    response.set_cookie(key="oauth_state", value=state, httponly=True, secure=True, samesite="lax", max_age=600)
    return response


@app.get("/to/discordbot")
async def to_discordbot(request: Request):
    auth = DiscordOAuth.create_from_db(discord_oauth_client, scopes=["identify", "applications.commands.permissions.update", "bot"])
    url, state = auth.get_authorization_url(permissions="8")
    response = RedirectResponse(url=url)
    response.set_cookie(key="oauth_state", value=state, httponly=True, secure=True, samesite="lax", max_age=600)
    return response


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
        self.server = None
        self.loop = None

    def run(self):
        cert_dir = Path(__file__).parent.parent / "database"
        certfile = cert_dir / "localhost+2.pem"
        keyfile = cert_dir / "localhost+2-key.pem"

        if certfile.exists() and keyfile.exists():
            config = uvicorn.Config(
                app,
                host="0.0.0.0",
                port=14000,
                ssl_certfile=str(certfile),
                ssl_keyfile=str(keyfile),
            )
        else:
            config = uvicorn.Config(app, host="0.0.0.0", port=14000)

        self.server = uvicorn.Server(config)

        # ⚠ 使用獨立 event loop，不使用 asyncio.run()
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        try:
            self.loop.run_until_complete(self.server.serve())
        except Exception as exc:
            capture_exception_safe(exc, tags={"service": "website", "source": "website_thread_run"})
            log.exception("Website thread crashed: %s", exc)
            raise
        finally:
            self.loop.close()

    def stop(self):
        if self.server:
            self.server.should_exit = True


if __name__ == "__main__":
    web = WebsiteThread()
    web.start()
