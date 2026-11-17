"""從後台邀請 bot：統一邀請流程（/to/discordbot?origin=）的後台分支，與 /oauth/discord 的 purpose=invite handler。

流程：/to/discordbot 帶 origin 時呼叫 invite_redirect，寫 dashboard_oauth cookie（purpose=invite）並導向 Discord 的邀請頁，
完成後 Discord 回到 /oauth/discord，由 auth.handle_dashboard_oauth 分流到這裡的 handler。
網站不交換 code、不保存 Discord 授權；去向依 session 的 Discord 帳號在實際加入的伺服器的權限決定。
"""

import asyncio
import logging
import time
from urllib.parse import urlencode

from fastapi.requests import Request
from fastapi.responses import RedirectResponse, Response

from . import auth
from .db import run_db
from .errors import DashboardError
from .guilds import bot_guild_ids, can_enter, guild_perms
from .session import SESSION_COOKIE, lookup_session

log = logging.getLogger(__name__)

#: 授權完成後等 bot 看到新伺服器的上限與輪詢間隔（秒）
WAIT_SECONDS = 5.0
POLL_INTERVAL = 0.5


def invite_redirect(url: str, state: str, origin: str | None) -> RedirectResponse:
    """導向 Discord 邀請頁，並記下這次邀請從後台發起：完成後回到 origin 的後台。"""
    cookie = auth.OAuthCookie(state=state, purpose="invite", next="/dashboard", origin=auth.sanitize_origin(origin))
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


def _login_redirect(origin: str) -> RedirectResponse:
    """沒有 session：導向前端的登入頁，登入後回到伺服器清單。"""
    return RedirectResponse(url=f"{origin}/dashboard-login?{urlencode({'next': '/dashboard/guilds'})}")


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
    origin = cookie.origin
    if params.get("error") or not params.get("code"):
        return RedirectResponse(url=f"{origin}/dashboard/guilds")

    # Discord 邀請頁登入的可能是另一個帳號；去向一律以 session 的帳號為準，不改 session
    session_id = request.cookies.get(SESSION_COOKIE)
    info = await run_db(lambda: lookup_session(session_id))
    if info is None:
        return _login_redirect(origin)

    guild_id = params.get("guild_id")
    log.info("Dashboard invite: user %s guild %s", info.discord_user_id, guild_id)
    return RedirectResponse(url=await _same_account_target(info.discord_user_id, guild_id, origin))


async def _same_account_target(user_id: str, guild_id: str | None, origin: str) -> str:
    if not guild_id or not guild_id.isdigit():
        return f"{origin}/dashboard/guilds"
    if not await _wait_for_bot(guild_id):
        return f"{origin}/dashboard/guilds?notice=invite_pending"
    try:
        perms = await guild_perms(user_id, guild_id)
    except DashboardError:
        return f"{origin}/dashboard/guilds"
    if can_enter(perms):
        return f"{origin}/dashboard/guilds/{guild_id}"
    return f"{origin}/dashboard/guilds?notice=need_permissions"


auth.register_oauth_purpose("invite", _handle_invite)
