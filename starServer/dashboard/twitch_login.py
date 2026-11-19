"""Twitch 登入：以 XingyuBot 自己的 Twitch 應用程式（OAuth client #3）直接授權，不經 auth server。

流程：/to/dashboard-twitch-login 寫 dashboard_twitch_oauth cookie 並導向 Twitch（空 scope，只識別身分），
Twitch 回到 /oauth/twitch，bot_website 先呼叫 handle_dashboard_twitch_oauth，回 None 才走原本的處理。
同一個 callback 靠 cookie 的 purpose 分派，後續的卡用 register_twitch_oauth_purpose 註冊自己的 purpose。

登入只識別身分：不存 token。實況主啟用 bot 時存下的完整 token 在同一筆 OAuthToken 上，這裡存了會被沒有 scope 的 token 蓋掉。
"""

import hmac
import logging
from collections.abc import Awaitable, Callable

from fastapi import APIRouter
from fastapi.requests import Request
from fastapi.responses import RedirectResponse, Response

from sentry_bootstrap import capture_exception_safe
from starlib import sqldb
from starlib.database import APIType, TwitchBotJoinChannel
from starlib.oauth import TwitchOAuth
from starlib.providers.social.models import TwitchUser
from starlib.utils import nowtz

from . import config
from .auth import OAUTH_COOKIE_MAX_AGE, OAuthCookie, decode_cookie, encode_cookie, sanitize_next, sanitize_origin
from .db import run_db
from .session import SESSION_COOKIE, TwitchIdentity, create_session, set_session_cookie

log = logging.getLogger(__name__)

to_router = APIRouter()

TWITCH_OAUTH_COOKIE = "dashboard_twitch_oauth"

# purpose -> handler(request, cookie)；W-03 註冊 enable
TwitchPurposeHandler = Callable[[Request, OAuthCookie], Awaitable[Response]]
_purpose_handlers: dict[str, TwitchPurposeHandler] = {}


def register_twitch_oauth_purpose(purpose: str, handler: TwitchPurposeHandler) -> None:
    _purpose_handlers[purpose] = handler


def delete_twitch_oauth_cookie(response: Response) -> None:
    response.delete_cookie(TWITCH_OAUTH_COOKIE, httponly=True, secure=True, samesite="lax")


# ====== Twitch OAuth client ======
_oauth_client_cache = None


async def get_oauth_client():
    global _oauth_client_cache
    if _oauth_client_cache is None:
        _oauth_client_cache = await run_db(lambda: sqldb.get_oauth_client(APIType.Twitch, config.TWITCH_OAUTH_SEQ))
    return _oauth_client_cache


async def new_twitch_oauth(scopes: list[str] | None = None) -> TwitchOAuth:
    return TwitchOAuth.create_from_db(await get_oauth_client(), scopes=scopes)


# ====== 登入入口 ======
@to_router.get("/to/dashboard-twitch-login")
async def to_dashboard_twitch_login(next: str | None = None, origin: str | None = None):
    # scope 為空：只識別身分，不要求任何權限
    async with await new_twitch_oauth([]) as auth:
        url, state = auth.get_authorization_url()
    cookie = OAuthCookie(state=state, purpose="login", next=sanitize_next(next), origin=sanitize_origin(origin))
    response = RedirectResponse(url=url)
    response.set_cookie(
        TWITCH_OAUTH_COOKIE,
        encode_cookie(cookie),
        max_age=OAUTH_COOKIE_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return response


# ====== /oauth/twitch 的後台分流 ======
async def handle_dashboard_twitch_oauth(request: Request) -> Response | None:
    """有 dashboard_twitch_oauth cookie 且 state 相符時處理並回應（一律清掉該 cookie）；否則回 None，由呼叫端走原本的處理。"""
    raw = request.cookies.get(TWITCH_OAUTH_COOKIE)
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
    delete_twitch_oauth_cookie(response)
    return response


def _record_channel(user: TwitchUser) -> None:
    """登入時登記頻道：沒有就新增 inactive 的一列，有就只更新顯示欄位，不動 state、指令、轉發設定。"""
    twitch_id = int(user.id)
    row = sqldb.get(TwitchBotJoinChannel, (twitch_id,))
    if row is None:
        sqldb.add(
            TwitchBotJoinChannel(
                twitch_id=twitch_id,
                login=user.login,
                display_name=user.display_name,
                avatar_url=user.profile_image_url,
                first_seen_at=nowtz(),
            )
        )
        return
    row.login = user.login
    row.display_name = user.display_name
    row.avatar_url = user.profile_image_url
    sqldb.merge(row)


async def _handle_login(request: Request, cookie: OAuthCookie) -> Response:
    params = request.query_params
    login_page = RedirectResponse(url=f"{cookie.origin}/dashboard-login")
    code = params.get("code")
    if params.get("error") or not code:
        return login_page

    try:
        # 只換身分：不呼叫 save_token_to_db，沒有 scope 的 token 會蓋掉已啟用頻道的完整 token
        async with await new_twitch_oauth([]) as auth:
            await auth.exchange_code(code)
            user = await auth.get_me()
        session_id = await run_db(lambda: _create_login_session(user, request.cookies.get(SESSION_COOKIE)))
    except Exception as exc:
        capture_exception_safe(exc, tags={"service": "website", "source": "dashboard_twitch_login"})
        log.exception("Dashboard Twitch login failed: %s", exc)
        return login_page

    log.info("Dashboard Twitch login: %s (%s)", user.login, user.id)
    next_path = f"/dashboard/channels/{user.id}" if cookie.next == "/dashboard" else cookie.next
    response = RedirectResponse(url=f"{cookie.origin}{next_path}")
    set_session_cookie(response, session_id)
    return response


def _create_login_session(user: TwitchUser, old_session_id: str | None) -> str:
    _record_channel(user)
    identity = TwitchIdentity(user.id, user.login, user.display_name, user.profile_image_url)
    return create_session(None, user.display_name, user.profile_image_url, old_session_id, twitch=identity)


register_twitch_oauth_purpose("login", _handle_login)
