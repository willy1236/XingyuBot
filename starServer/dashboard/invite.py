"""從後台清單邀請 bot：/to/dashboard-invite 與 /oauth/discord 的 purpose=invite 分支。

流程：/to/dashboard-invite 寫 dashboard_oauth cookie（purpose=invite）並導向 Discord 的 bot 授權頁，
完成後 Discord 回到 /oauth/discord，由 auth.handle_dashboard_oauth 分流到這裡的 handler。
"""

import asyncio
import logging
import time
from urllib.parse import urlencode

from fastapi import APIRouter
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from sentry_bootstrap import capture_exception_safe

from . import auth
from .db import run_db
from .errors import DashboardError
from .guilds import bot_guild_ids, guild_perms, invalidate
from .session import SESSION_COOKIE, create_session, lookup_session, set_session_cookie

log = logging.getLogger(__name__)

to_router = APIRouter()

INVITE_SCOPES = ["bot", "identify", "guilds"]
#: 授權完成後等 bot 看到新伺服器的上限與輪詢間隔（秒）
WAIT_SECONDS = 5.0
POLL_INTERVAL = 0.5


def _login_redirect(origin: str) -> RedirectResponse:
    query = urlencode({"next": "/dashboard", "origin": origin})
    return RedirectResponse(url=f"/to/dashboard-login?{query}")


@to_router.get("/to/dashboard-invite")
async def to_dashboard_invite(request: Request, guild_id: str | None = None, origin: str | None = None):
    origin = auth.sanitize_origin(origin)
    session_id = request.cookies.get(SESSION_COOKIE)
    if await run_db(lambda: lookup_session(session_id)) is None:
        return _login_redirect(origin)

    extra = {"permissions": "8"}
    if guild_id and guild_id.isdigit():
        extra |= {"guild_id": guild_id, "disable_guild_select": "false"}
    async with await auth.new_discord_oauth(INVITE_SCOPES) as oauth:
        url, state = oauth.get_authorization_url(**extra)
    cookie = auth.OAuthCookie(state=state, purpose="invite", next="/dashboard", origin=origin)
    response = RedirectResponse(url=url)
    response.set_cookie(
        auth.OAUTH_COOKIE,
        auth._encode_cookie(cookie),
        max_age=auth.OAUTH_COOKIE_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return response


async def _wait_for_bot(guild_id: str) -> bool:
    """等 bot 看到實際加入的伺服器；bot 尚未 ready 視同還沒看到。"""
    deadline = time.monotonic() + WAIT_SECONDS
    while True:
        try:
            if guild_id in await bot_guild_ids():
                return True
        except DashboardError:
            pass
        if time.monotonic() >= deadline:
            return False
        await asyncio.sleep(POLL_INTERVAL)


async def _handle_invite(request: Request, cookie: auth.OAuthCookie) -> Response:
    params = request.query_params
    code = params.get("code")
    origin = cookie.origin
    if params.get("error") or not code:
        return RedirectResponse(url=f"{origin}/dashboard")

    try:
        async with await auth.new_discord_oauth(INVITE_SCOPES) as oauth:
            await oauth.exchange_code(code)
            user = await oauth.get_me()
            await run_db(lambda: oauth.save_token_to_db(user.id))
    except Exception as exc:
        capture_exception_safe(exc, tags={"service": "website", "source": "dashboard_invite"})
        log.exception("Dashboard invite failed: %s", exc)
        return HTMLResponse("授權失敗，請重新開始邀請", 400)

    invalidate(user.id)

    old_id = request.cookies.get(SESSION_COOKIE)
    old = await run_db(lambda: lookup_session(old_id))
    same_account = old is not None and old.discord_user_id == user.id
    new_session_id: str | None = None
    if not same_account:
        name = user.global_name or user.username
        new_session_id = await run_db(lambda: create_session(user.id, name, user.avatar, old_id))

    # Discord 邀請頁登入的是另一個帳號：以該帳號登入，回清單
    if old is not None and not same_account:
        target = f"{origin}/dashboard"
    else:
        target = await _same_account_target(user.id, params.get("guild_id"), origin)

    log.info("Dashboard invite: user %s guild %s", user.id, params.get("guild_id"))
    response = RedirectResponse(url=target)
    if new_session_id is not None:
        set_session_cookie(response, new_session_id)
    return response


async def _same_account_target(user_id: str, guild_id: str | None, origin: str) -> str:
    if not guild_id or not guild_id.isdigit():
        return f"{origin}/dashboard"
    if not await _wait_for_bot(guild_id):
        return f"{origin}/dashboard?notice=invite_pending"
    try:
        perms = await guild_perms(user_id, guild_id)
    except DashboardError:
        return f"{origin}/dashboard"
    if perms.manage_channels:
        return f"{origin}/dashboard/guilds/{guild_id}"
    return f"{origin}/dashboard?notice=need_manage_channels"


auth.register_oauth_purpose("invite", _handle_invite)
