"""Discord 登入、登出與 /dashboard/me。

登入流程：/to/dashboard-login 寫 dashboard_oauth cookie 並導向 Discord，Discord 回到 /oauth/discord，
bot_website 先呼叫 handle_dashboard_oauth，回 None 才走原本的處理。
"""

import base64
import hmac
import json
import logging
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel

from sentry_bootstrap import capture_exception_safe
from starlib import sqldb
from starlib.database import APIType
from starlib.oauth import DiscordOAuth

from . import config
from .db import run_db
from .session import (
    SESSION_COOKIE,
    DiscordSessionInfo,
    SessionInfo,
    create_session,
    delete_session_cookie,
    delete_twitch_user_sessions,
    delete_user_sessions,
    follow_account,
    require_any_session,
    set_session_cookie,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard")
to_router = APIRouter()

OAUTH_COOKIE = "dashboard_oauth"
OAUTH_COOKIE_MAX_AGE = 600
LOGIN_SCOPES = ["identify"]


class OAuthCookie(BaseModel):
    state: str
    purpose: str
    next: str = "/dashboard"
    origin: str = ""
    #: Twitch 啟用 bot 時要啟用的頻道（purpose=enable）；其他流程沒有
    channel_id: str | None = None


# purpose -> handler(request, cookie)；T-09 在 invite.py 註冊 invite
OAuthPurposeHandler = Callable[[Request, OAuthCookie], Awaitable[Response]]
_purpose_handlers: dict[str, OAuthPurposeHandler] = {}


def register_oauth_purpose(purpose: str, handler: OAuthPurposeHandler) -> None:
    _purpose_handlers[purpose] = handler


# ====== 驗證 next 與 origin（寫入 cookie 與從 cookie 讀出時用同一套規則） ======
def sanitize_next(value: str | None) -> str:
    """只接受 /dashboard 開頭的站內相對路徑，其他一律改成 /dashboard。"""
    default = "/dashboard"
    if not value or not value.startswith(default):
        return default
    rest = value[len(default) :]
    if rest and rest[0] not in "/?":
        return default
    if any(ord(c) < 0x20 or c == "\\" for c in value):
        return default
    return value


def sanitize_origin(value: str | None) -> str:
    """必須在 DASHBOARD_ALLOWED_ORIGINS 裡，不在或沒帶就用 DASHBOARD_FRONTEND_URL。"""
    if value and value in config.allowed_origins():
        return value
    return config.frontend_url()


def encode_cookie(cookie: OAuthCookie) -> str:
    return base64.urlsafe_b64encode(cookie.model_dump_json(exclude_none=True).encode()).decode()


def decode_cookie(raw: str) -> OAuthCookie | None:
    try:
        return OAuthCookie(**json.loads(base64.urlsafe_b64decode(raw.encode())))
    except Exception:
        return None


def _delete_oauth_cookie(response: Response) -> None:
    response.delete_cookie(OAUTH_COOKIE, httponly=True, secure=True, samesite="lax")


# ====== Discord OAuth client ======
_oauth_client_cache = None


async def get_oauth_client():
    global _oauth_client_cache
    if _oauth_client_cache is None:
        _oauth_client_cache = await run_db(lambda: sqldb.get_oauth_client(APIType.Discord, config.DISCORD_OAUTH_SEQ))
    return _oauth_client_cache


async def new_discord_oauth(scopes: list[str] | None = None) -> DiscordOAuth:
    return DiscordOAuth.create_from_db(await get_oauth_client(), scopes=scopes)


# ====== 登入入口 ======
@to_router.get("/to/dashboard-login")
async def to_dashboard_login(next: str | None = None, origin: str | None = None):
    async with await new_discord_oauth(LOGIN_SCOPES) as auth:
        url, state = auth.get_authorization_url()
    cookie = OAuthCookie(state=state, purpose="login", next=sanitize_next(next), origin=sanitize_origin(origin))
    response = RedirectResponse(url=url)
    response.set_cookie(
        OAUTH_COOKIE, encode_cookie(cookie), max_age=OAUTH_COOKIE_MAX_AGE, httponly=True, secure=True, samesite="lax"
    )
    return response


# ====== /oauth/discord 的後台分流 ======
async def handle_dashboard_oauth(request: Request) -> Response | None:
    """有 dashboard_oauth cookie 且 state 相符時處理並回應（一律清掉該 cookie）；否則回 None，由呼叫端走原本的處理。"""
    raw = request.cookies.get(OAUTH_COOKIE)
    if raw is None:
        return None
    cookie = decode_cookie(raw)
    state = request.query_params.get("state")
    if cookie is None or state is None or not hmac.compare_digest(cookie.state.encode(), state.encode()):
        return None

    # cookie 沒有簽章，同 site 的子網域可以寫入，讀出後用同一套規則再驗一次
    cookie.next = sanitize_next(cookie.next)
    cookie.origin = sanitize_origin(cookie.origin)

    handler = _purpose_handlers.get(cookie.purpose)
    if handler is None:
        response = RedirectResponse(url=f"{cookie.origin}/dashboard")
    else:
        response = await handler(request, cookie)
    _delete_oauth_cookie(response)
    return response


async def _handle_login(request: Request, cookie: OAuthCookie) -> Response:
    params = request.query_params
    code = params.get("code")
    if params.get("error") or not code:
        return RedirectResponse(url=f"{cookie.origin}/")

    try:
        async with await new_discord_oauth(LOGIN_SCOPES) as auth:
            await auth.exchange_code(code)
            user = await auth.get_me()
    except Exception as exc:
        capture_exception_safe(exc, tags={"service": "website", "source": "dashboard_login"})
        log.exception("Dashboard login failed: %s", exc)
        return HTMLResponse("授權失敗，請重新開始登入", 400)

    name = user.global_name or user.username
    old_session_id = request.cookies.get(SESSION_COOKIE)
    session_id = await run_db(lambda: create_session(user.id, name, user.avatar, old_session_id))
    # 立即確認一次析域帳號，登入後的第一個請求就帶得到
    await follow_account(DiscordSessionInfo(session_id, user.id, name, user.avatar), force=True)
    log.info("Dashboard login: user %s (%s)", user.username, user.id)

    response = RedirectResponse(url=f"{cookie.origin}{cookie.next}")
    set_session_cookie(response, session_id)
    return response


register_oauth_purpose("login", _handle_login)


# ====== /dashboard/me、/dashboard/logout ======
def avatar_url(user_id: str, avatar: str | None) -> str:
    if avatar:
        ext = "gif" if avatar.startswith("a_") else "png"
        return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar}.{ext}"
    # 新版 username 系統的預設頭像
    return f"https://cdn.discordapp.com/embed/avatars/{(int(user_id) >> 22) % 6}.png"


@router.get("/me")
async def me(info: SessionInfo = Depends(require_any_session)):
    account = None if info.account_id is None else {"username": info.account_username}
    if info.discord_user_id is not None:
        avatar = avatar_url(info.discord_user_id, info.avatar)
    else:
        avatar = info.avatar
    return {
        "id": info.identity_key,
        "name": info.name,
        "avatar_url": avatar,
        "discord": None if info.discord_user_id is None else {"id": info.discord_user_id},
        "twitch": None if info.twitch is None else {"id": info.twitch.id, "login": info.twitch.login},
        "account": account,
        "login_method": info.login_method,
        "has_channels": len(info.twitch_channels) > 0,
    }


@router.post("/logout")
async def logout(request: Request, info: SessionInfo = Depends(require_any_session)):
    """刪除這個登入身分所有裝置的 session 並清 cookie：Twitch 登入以 Twitch 帳號為單位，其餘以 Discord 帳號為單位。
    網站不保存 Discord 授權，Discord 端的授權不受影響。"""
    twitch, discord_id = info.twitch, info.discord_user_id
    if info.login_method == "twitch" and twitch is not None:
        await run_db(lambda: delete_twitch_user_sessions(twitch.id))
    elif discord_id is not None:
        await run_db(lambda: delete_user_sessions(discord_id))

    request.state.dashboard_renew_session = None
    response = JSONResponse({"ok": True})
    delete_session_cookie(response)
    return response
