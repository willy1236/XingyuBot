"""實況主啟用與停用 bot。

GET  /to/dashboard-twitch-enable?channel=&origin=  整頁導覽：到 Twitch 授權完整權限（purpose=enable）
GET  /oauth/twitch（由 twitch_login 分派）          enable handler：比對帳號、存 token、設 mod、啟用、通知 bot
POST /dashboard/channels/{twitch_id}/disable        停用：bot 離開，資料與 token 保留

整頁導覽的失敗一律導回前端頁面並帶 `?notice=<代碼>`（多個以逗號分隔），不回 JSON。
"""

import logging
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends
from fastapi.requests import Request
from fastapi.responses import RedirectResponse, Response

from sentry_bootstrap import capture_exception_safe
from starlib import sqldb
from starlib.database import TwitchBotJoinChannel
from starlib.messaging.rpc import RpcHandlerError
from starlib.twitch_tokens import MODERATORS_URL, bot_user_id_blocking

from . import twitch_control
from .auth import OAuthCookie, sanitize_origin
from .channels import CHANNEL_LIST_PATH, DEFAULT_STATE, channel_page_path, find_channel, require_channel
from .db import run_db
from .session import SESSION_COOKIE, TwitchIdentity, lookup_followed_session
from .twitch_login import (
    get_oauth_client,
    new_twitch_oauth,
    record_channel,
    redirect_to_twitch,
    register_twitch_oauth_purpose,
)

log = logging.getLogger(__name__)

to_router = APIRouter()
router = APIRouter(prefix="/dashboard")

#: 實況主授權給 bot 的權限；twitch_chatbot.USER_SCOPE 是 bot 帳號自己的，不要混用
ENABLE_SCOPES = [
    "channel:manage:moderators",
    "moderation:read",
    "moderator:read:followers",
    "channel:read:subscriptions",
    "channel:read:redemptions",
    "channel:read:predictions",
    "user:read:blocked_users",
]

REQUEST_TIMEOUT = 5.0


def _channel_url(origin: str, channel_id: int | str) -> str:
    return f"{origin}{channel_page_path(channel_id)}"


def _with_notice(url: str, *notices: str) -> str:
    return f"{url}?notice={','.join(notices)}" if notices else url


def _login_url(origin: str, channel_id: int | str) -> str:
    return f"{origin}/dashboard-login?{urlencode({'next': channel_page_path(channel_id)})}"


# ====== 啟用入口 ======
@to_router.get("/to/dashboard-twitch-enable")
async def to_dashboard_twitch_enable(request: Request, channel: str | None = None, origin: str | None = None):
    origin = sanitize_origin(origin)
    if channel is None or not channel.isdecimal():
        return RedirectResponse(url=f"{origin}{CHANNEL_LIST_PATH}")
    channel_id = int(channel)

    info = await lookup_followed_session(request.cookies.get(SESSION_COOKIE))
    if info is None:
        return RedirectResponse(url=_login_url(origin, channel_id))
    # 不是自己的頻道：導回頻道頁，由 ChannelAccessGuard 顯示「沒有這個頻道的權限」
    if find_channel(info, channel_id) is None:
        return RedirectResponse(url=_channel_url(origin, channel_id))
    # W-12：頻道被停權時在這裡導回並帶 notice=channel_banned

    async with await new_twitch_oauth(ENABLE_SCOPES) as auth:
        # force_verify：瀏覽器已登入另一個 Twitch 帳號時，使用者才有機會換帳號
        url, state = auth.get_authorization_url(force_verify="true")
    cookie = OAuthCookie(state=state, purpose="enable", next="/dashboard", origin=origin, channel_id=str(channel_id))
    return redirect_to_twitch(url, cookie)


# ====== Twitch API ======
async def _add_bot_as_mod(broadcaster_id: str, access_token: str) -> bool:
    """用實況主的 token 把 bot 帳號設為頻道 mod；已經是 mod 視為成功。失敗回 False，不 raise。

    Twitch 對「已經是 mod」回 400，但訊息內容沒有保證；所以 400 時改查 mod 名單，bot 在名單裡才算成功。

    常見失敗：401／403 缺權限、422 bot 目前是頻道 VIP（要先移除）、429 速率限制。
    """
    try:
        bot_id = await run_db(bot_user_id_blocking)
        client_id = (await get_oauth_client()).client_id
        params = {"broadcaster_id": broadcaster_id, "user_id": bot_id}
        headers = {"Authorization": f"Bearer {access_token}", "Client-Id": client_id}
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.post(MODERATORS_URL, params=params, headers=headers)
            if response.status_code == 400:
                listing = await client.get(MODERATORS_URL, params=params, headers=headers)
                if listing.status_code == 200 and listing.json()["data"]:
                    return True
    except Exception as exc:
        capture_exception_safe(exc, tags={"service": "website", "source": "dashboard_twitch_add_mod"})
        log.exception("Twitch Add Channel Moderator failed for %s: %s", broadcaster_id, exc)
        return False
    if response.status_code == 204:
        return True
    log.warning("Twitch Add Channel Moderator for %s: %s %s", broadcaster_id, response.status_code, response.text)
    capture_exception_safe(
        RuntimeError(f"Add Channel Moderator {response.status_code}: {response.text}"),
        tags={"service": "website", "source": "dashboard_twitch_add_mod"},
    )
    return False


# ====== enable handler ======
async def _sync_bot(twitch_id: int) -> bool:
    """通知 bot 依資料庫的 state 加入或離開頻道；回傳 bot 是否沒有完成同步（離線或內部出錯）。"""
    try:
        return isinstance(await twitch_control.sync_channel(twitch_id), twitch_control.BotOffline)
    except RpcHandlerError as exc:
        capture_exception_safe(exc, tags={"service": "website", "source": "dashboard_twitch_sync"})
        log.exception("Twitch bot sync failed for %s: %s", twitch_id, exc)
        return True


async def _handle_enable(request: Request, cookie: OAuthCookie) -> Response:
    origin = cookie.origin
    channel_id = cookie.channel_id
    if channel_id is None or not channel_id.isdecimal():
        return RedirectResponse(url=f"{origin}{CHANNEL_LIST_PATH}")
    channel_url = _channel_url(origin, channel_id)

    params = request.query_params
    code = params.get("code")
    if params.get("error") or not code:
        return RedirectResponse(url=channel_url)

    info = await lookup_followed_session(request.cookies.get(SESSION_COOKIE))
    if info is None:
        return RedirectResponse(url=_login_url(origin, channel_id))
    if find_channel(info, int(channel_id)) is None:
        return RedirectResponse(url=channel_url)

    try:
        async with await new_twitch_oauth(ENABLE_SCOPES) as auth:
            token = await auth.exchange_code(code)
            user = await auth.get_me()
            # 授權的帳號不是頻道本人：視同授權失敗，不保存 token
            if user.id != channel_id:
                return RedirectResponse(url=_with_notice(channel_url, "wrong_account"))
            await run_db(lambda: auth.save_token_to_db(user.id))
    except Exception as exc:
        capture_exception_safe(exc, tags={"service": "website", "source": "dashboard_twitch_enable"})
        log.exception("Dashboard Twitch enable failed for %s: %s", channel_id, exc)
        return RedirectResponse(url=_with_notice(channel_url, "enable_failed"))

    notices: list[str] = []
    # 設 mod 失敗不擋啟用：後台提示實況主手動輸入 /mod，W-08 會持續標示直到修好
    if not await _add_bot_as_mod(user.id, token.get("access_token", "")):
        notices.append("mod_failed")

    try:
        await run_db(lambda: record_channel(user, state="enabled"))
    except Exception as exc:
        capture_exception_safe(exc, tags={"service": "website", "source": "dashboard_twitch_enable"})
        log.exception("Dashboard Twitch enable: saving channel %s failed: %s", channel_id, exc)
        return RedirectResponse(url=_with_notice(channel_url, "enable_failed"))
    log.info("Dashboard Twitch enable: %s (%s)", user.login, user.id)

    if await _sync_bot(int(channel_id)):
        notices.append("bot_offline")
    return RedirectResponse(url=_with_notice(channel_url, *notices))


register_twitch_oauth_purpose("enable", _handle_enable)


# ====== 停用 ======
def _disable(twitch_id: int) -> str:
    """enabled 改成 disabled，回傳之後的 state；其他 state 不動（沒有頻道列視為 inactive）。"""
    row = sqldb.get(TwitchBotJoinChannel, (twitch_id,))
    if row is None:
        return DEFAULT_STATE
    if row.state == "enabled":
        row.state = "disabled"
        sqldb.merge(row)
    return row.state


@router.post("/channels/{twitch_id}/disable")
async def disable_channel(twitch_id: int, _: TwitchIdentity = Depends(require_channel)):
    state = await run_db(lambda: _disable(twitch_id))
    # disabled 時才通知 bot；已經是 disabled 再按一次也照樣通知，讓上次沒完成的離開有機會補上
    bot_offline = await _sync_bot(twitch_id) if state == "disabled" else False
    return {"state": state, "bot_offline": bot_offline}
