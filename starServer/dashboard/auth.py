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
    SessionInfo,
    create_session,
    delete_session_cookie,
    delete_user_sessions,
    require_session,
    set_session_cookie,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard")
to_router = APIRouter()

OAUTH_COOKIE = "dashboard_oauth"
OAUTH_COOKIE_MAX_AGE = 600
LOGIN_SCOPES = ["identify", "guilds"]


class OAuthCookie(BaseModel):
    state: str
    purpose: str
    next: str = "/dashboard"
    origin: str = ""


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


def _encode_cookie(cookie: OAuthCookie) -> str:
    return base64.urlsafe_b64encode(cookie.model_dump_json().encode()).decode()


def _decode_cookie(raw: str) -> OAuthCookie | None:
    try:
        return OAuthCookie(**json.loads(base64.urlsafe_b64decode(raw.encode())))
    except Exception:
        return None


def _delete_oauth_cookie(response: Response) -> None:
    response.delete_cookie(OAUTH_COOKIE, httponly=True, secure=True, samesite="lax")


# ====== Discord OAuth client ======
_oauth_client_cache = None


async def _get_oauth_client():
    global _oauth_client_cache
    if _oauth_client_cache is None:
        _oauth_client_cache = await run_db(lambda: sqldb.get_oauth_client(APIType.Discord, config.DISCORD_OAUTH_SEQ))
    return _oauth_client_cache


async def new_discord_oauth(scopes: list[str] | None = None) -> DiscordOAuth:
    return DiscordOAuth.create_from_db(await _get_oauth_client(), scopes=scopes)


# ====== 登入入口 ======
@to_router.get("/to/dashboard-login")
async def to_dashboard_login(next: str | None = None, origin: str | None = None):
    async with await new_discord_oauth(LOGIN_SCOPES) as auth:
        url, state = auth.get_authorization_url()
    cookie = OAuthCookie(state=state, purpose="login", next=sanitize_next(next), origin=sanitize_origin(origin))
    response = RedirectResponse(url=url)
    response.set_cookie(
        OAUTH_COOKIE, _encode_cookie(cookie), max_age=OAUTH_COOKIE_MAX_AGE, httponly=True, secure=True, samesite="lax"
    )
    return response


# ====== /oauth/discord 的後台分流 ======
async def handle_dashboard_oauth(request: Request) -> Response | None:
    """有 dashboard_oauth cookie 且 state 相符時處理並回應（一律清掉該 cookie）；否則回 None，由呼叫端走原本的處理。"""
    raw = request.cookies.get(OAUTH_COOKIE)
    if raw is None:
        return None
    cookie = _decode_cookie(raw)
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
            await run_db(lambda: auth.save_token_to_db(user.id))
    except Exception as exc:
        capture_exception_safe(exc, tags={"service": "website", "source": "dashboard_login"})
        log.exception("Dashboard login failed: %s", exc)
        return HTMLResponse("授權失敗，請重新開始登入", 400)

    name = user.global_name or user.username
    old_session_id = request.cookies.get(SESSION_COOKIE)
    session_id = await run_db(lambda: create_session(user.id, name, user.avatar, old_session_id))
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
async def me(info: SessionInfo = Depends(require_session)):
    return {"id": info.discord_user_id, "name": info.name, "avatar_url": avatar_url(info.discord_user_id, info.avatar)}


def _delete_token(user_id: str, credential_id: int) -> str | None:
    """刪除使用者的 OAuthToken，回傳原本的 access token（沒有就回 None）。"""
    token = sqldb.get_oauth_token(user_id, credential_id)
    if token is None:
        return None
    access_token = token.access_token
    sqldb.session.delete(token)
    sqldb.session.commit()
    return access_token


@router.post("/logout")
async def logout(request: Request, info: SessionInfo = Depends(require_session)):
    """撤銷 Discord 授權、刪除該使用者所有 session 與 OAuthToken、清 cookie。

    Discord 端撤銷失敗（網路或授權早已失效）不擋登出，本地資料仍照常清掉。
    """
    client = await _get_oauth_client()
    access_token = await run_db(lambda: _delete_token(info.discord_user_id, client.credential_id))
    if access_token is not None:
        try:
            async with DiscordOAuth.create_from_db(client) as auth:
                await auth.revoke_token(access_token)
        except Exception as exc:
            capture_exception_safe(exc, tags={"service": "website", "source": "dashboard_logout_revoke"})
            log.warning("Dashboard logout: revoke failed for %s: %s", info.discord_user_id, exc)
    await run_db(lambda: delete_user_sessions(info.discord_user_id))

    request.state.dashboard_renew_session = None
    response = JSONResponse({"ok": True})
    delete_session_cookie(response)
    return response
