"""後台 session：30 天滑動，存在 DashboardSession；session 帶的析域帳號每 60 秒向 auth server 重新確認一次。

session 的身分是一個 Discord 帳號或一個 Twitch 帳號（login_method 區分），析域帳號是附帶欄位。帳號跟隨的確認結果存在記憶體（以 session ID 為 key），
auth server 暫時不可用時沿用上次結果，重啟後則以資料庫的 account_id 為準。
Discord 登入的 session 只跟著帳號升級或降級；析域登入的 session 在域民停權、查無或不再連結這個 Discord 時失效；
Twitch 登入的 session 不附帶析域帳號，不做帳號跟隨。

require_session 只放行有 Discord 身分的 session（伺服器與個人區端點），require_any_session 只要求已登入。
"""

import asyncio
import dataclasses
import logging
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from fastapi.requests import Request
from sqlalchemy import delete, update

from starlib import sqldb, website_stats
from starlib.database import DashboardSession
from starlib.identity import Account, DirectoryUnavailable
from starlib.identity.resolver import get_directory
from starlib.utils import nowtz

from .db import run_db
from .errors import DashboardError

log = logging.getLogger(__name__)

SESSION_COOKIE = "dashboard_session"
SESSION_TTL = timedelta(days=30)
#: 帳號跟隨的重新確認間隔，也是 auth server 不可用後暫停查詢的時間（秒）
FOLLOW_INTERVAL = 60.0


@dataclass(frozen=True)
class TwitchIdentity:
    id: str
    login: str
    name: str
    avatar: str | None


@dataclass(frozen=True)
class SessionInfo:
    session_id: str
    #: 沒有 Discord 身分（Twitch 登入）時為 None
    discord_user_id: str | None
    name: str
    avatar: str | None
    #: 這個 session 帶的析域帳號；沒有連結時為 None
    account_id: UUID | None = None
    #: 域民代號；有析域帳號但 auth server 暫時查不到時為 None
    account_username: str | None = None
    #: 是否由析域登入建立
    via_domalyze: bool = False
    #: 該域民連結的 Discord ID（依數值由小到大）；沒有析域帳號時為空
    discord_ids: tuple[int, ...] = ()
    #: 析域帳號資訊是否沿用舊結果（auth server 暫時不可用）
    stale: bool = False
    #: discord、domalyze 或 twitch
    login_method: str = "discord"
    twitch: TwitchIdentity | None = None
    #: 這個 session 可以管理的 Twitch 頻道；頻道端點只用這個判斷，不自己查
    twitch_channels: tuple[TwitchIdentity, ...] = ()

    @property
    def identity_key(self) -> str:
        """主身分 key：有 Discord 時是 Discord ID，Twitch 登入是 twitch:<id>，沒有 Discord 的析域登入是 domalyze:<account_id>。"""
        if self.discord_user_id is not None:
            return self.discord_user_id
        if self.twitch is not None:
            return f"twitch:{self.twitch.id}"
        return f"domalyze:{self.account_id}"


@dataclass(frozen=True)
class DiscordSessionInfo(SessionInfo):
    """保證有 Discord 身分的 session；require_session 回傳這個型別。"""

    discord_user_id: str


def _now() -> datetime:
    return nowtz()


def set_session_cookie(response, session_id: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, session_id, max_age=int(SESSION_TTL.total_seconds()), httponly=True, secure=True, samesite="lax"
    )


def delete_session_cookie(response) -> None:
    response.delete_cookie(SESSION_COOKIE, httponly=True, secure=True, samesite="lax")


def _info(row: DashboardSession) -> SessionInfo:
    twitch = (
        None
        if row.twitch_user_id is None
        else TwitchIdentity(row.twitch_user_id, row.twitch_login or "", row.twitch_name or "", row.twitch_avatar)
    )
    extra = {
        "account_id": row.account_id,
        "via_domalyze": row.via_domalyze,
        "login_method": row.login_method,
        "twitch": twitch,
        "twitch_channels": (twitch,) if twitch is not None and row.login_method == "twitch" else (),
    }
    if row.discord_user_id is None:
        return SessionInfo(row.session_id, None, row.name, row.avatar, **extra)
    return DiscordSessionInfo(row.session_id, row.discord_user_id, row.name, row.avatar, **extra)


def _touch(session_id: str) -> SessionInfo | None:
    """查到未過期的 session 就更新最後使用時間並回傳；過期的順手刪掉。"""
    s = sqldb.session
    row = s.get(DashboardSession, session_id, populate_existing=True)
    if row is None:
        return None
    now = _now()
    if now - row.last_used_at > SESSION_TTL:
        s.delete(row)
        s.commit()
        return None
    row.last_used_at = now
    s.add(row)
    s.commit()
    return _info(row)


def lookup_session(session_id: str | None) -> SessionInfo | None:
    """只讀地查 session：不續期、不刪除、不做帳號跟隨；沒帶、不存在或已過期回 None。"""
    if not session_id:
        return None
    row = sqldb.session.get(DashboardSession, session_id, populate_existing=True)
    if row is None or _now() - row.last_used_at > SESSION_TTL:
        return None
    return _info(row)


def create_session(
    discord_user_id: str | None,
    name: str,
    avatar: str | None,
    replace_session_id: str | None = None,
    *,
    account_id: UUID | None = None,
    via_domalyze: bool = False,
    twitch: TwitchIdentity | None = None,
) -> str:
    """建立新 session，登入方式由參數決定：帶 twitch 是 Twitch 登入，via_domalyze 是析域登入，其餘是 Discord 登入。

    cookie 帶著的舊 session（不論是不是同一個帳號）一併刪掉，換帳號時就不會留著舊帳號的 session。
    """
    if twitch is not None and (via_domalyze or discord_user_id is not None):
        raise ValueError("Twitch 登入的 session 不帶 Discord 身分，也不是析域登入")
    if twitch is None and discord_user_id is None and not (via_domalyze and account_id is not None):
        raise ValueError("session 需要 Discord 身分、Twitch 身分，或析域登入的析域帳號")
    login_method = "twitch" if twitch is not None else "domalyze" if via_domalyze else "discord"
    s = sqldb.session
    # 順手清掉已過期的 session，沒有人再用到的列才不會一直留在表裡
    s.execute(delete(DashboardSession).where(DashboardSession.last_used_at < _now() - SESSION_TTL))  # pyright: ignore[reportArgumentType]
    if replace_session_id:
        s.execute(delete(DashboardSession).where(DashboardSession.session_id == replace_session_id))  # pyright: ignore[reportArgumentType]
        _followed.pop(replace_session_id, None)
    _prune_followed()
    session_id = secrets.token_urlsafe(32)
    s.add(
        DashboardSession(  # pyright: ignore[reportCallIssue] 自訂 __table_args__ 的 model，pyright 誤判為必填欄位
            session_id=session_id,
            discord_user_id=discord_user_id,
            name=name,
            avatar=avatar,
            account_id=account_id,
            via_domalyze=via_domalyze,
            login_method=login_method,
            twitch_user_id=None if twitch is None else twitch.id,
            twitch_login=None if twitch is None else twitch.login,
            twitch_name=None if twitch is None else twitch.name,
            twitch_avatar=None if twitch is None else twitch.avatar,
        )
    )
    s.commit()
    return session_id


def _delete_sessions_where(condition) -> None:
    s = sqldb.session
    deleted = s.execute(
        delete(DashboardSession).where(condition).returning(DashboardSession.session_id)  # pyright: ignore[reportArgumentType, reportCallIssue]
    ).scalars()
    for session_id in deleted:
        _followed.pop(session_id, None)
        # 進行中的確認跑完時看到自己已不在 _inflight，就不會把結果寫回 _followed
        _inflight.pop(session_id, None)
    s.commit()


def delete_user_sessions(discord_user_id: str) -> None:
    _delete_sessions_where(DashboardSession.discord_user_id == discord_user_id)


def delete_twitch_user_sessions(twitch_user_id: str) -> None:
    _delete_sessions_where(DashboardSession.twitch_user_id == twitch_user_id)


# ====== 帳號跟隨 ======
@dataclass(frozen=True)
class _Followed:
    checked_at: float
    account_id: UUID | None
    account_username: str | None
    discord_ids: tuple[int, ...]
    stale: bool
    #: 析域登入的 session 已失效（只在確認當下使用，不存進 _followed）
    revoked: bool = False


# session ID -> 最近一次確認結果
_followed: dict[str, _Followed] = {}
# session ID -> 進行中的確認；同一個 session 同時到的請求共用同一次
_inflight: dict[str, asyncio.Task[_Followed]] = {}
# auth server 不可用後，這個時間點（monotonic）之前不再查詢
_unavailable_until = 0.0


def _prune_followed() -> None:
    """清掉超過 session 有效期沒再確認的項目：那些 session 已過期，或已在別處被刪除。"""
    cutoff = time.monotonic() - SESSION_TTL.total_seconds()
    for session_id in [k for k, v in _followed.items() if v.checked_at < cutoff]:
        del _followed[session_id]


def remember_account(session_id: str, account: Account) -> None:
    """記下剛登入時已查到的析域帳號，登入後的第一個請求不必再向 auth server 確認。"""
    _followed[session_id] = _Followed(
        time.monotonic(), account.account_id, account.username, account.discord_ids, False
    )


def _delete_session(session_id: str) -> None:
    s = sqldb.session
    s.execute(delete(DashboardSession).where(DashboardSession.session_id == session_id))  # pyright: ignore[reportArgumentType]
    s.commit()
    _followed.pop(session_id, None)


def _save_account_id(session_id: str, account_id: UUID | None) -> None:
    s = sqldb.session
    s.execute(
        update(DashboardSession).where(DashboardSession.session_id == session_id).values(account_id=account_id)  # pyright: ignore[reportArgumentType]
    )
    s.commit()


def _fallback(info: SessionInfo, previous: _Followed | None, now: float) -> _Followed:
    """auth server 不可用：有舊結果就沿用，沒有就以資料庫的 account_id 為準，代號未知、只帶 session 的 Discord。"""
    if previous is not None:
        return dataclasses.replace(previous, checked_at=now, stale=True)
    has_discord = info.account_id is not None and info.discord_user_id is not None
    discord_ids = (int(info.discord_user_id),) if has_discord else ()  # pyright: ignore[reportArgumentType]
    return _Followed(now, info.account_id, None, discord_ids, True)


async def _check(info: SessionInfo, now: float) -> _Followed:
    """Discord 登入的 session：以這個 Discord 目前連結、未停權的域民為準（合併後就是存續帳號）。
    析域登入的 session：以 session 的域民為準（合併後改帶存續帳號）；查無、停權或不再連結這個 Discord 時失效。

    Raises:
        DirectoryUnavailable: auth server 沒給出明確答案。
    """
    discord_id = None if info.discord_user_id is None else int(info.discord_user_id)
    if info.via_domalyze:
        resolved = None if info.account_id is None else await get_directory().find_by_account_id(info.account_id)
        account = None if resolved is None else resolved.account
        if account is None or account.suspended or (discord_id is not None and discord_id not in account.discord_ids):
            return _Followed(now, None, None, (), False, revoked=True)
        return _Followed(now, account.account_id, account.username, account.discord_ids, False)

    if discord_id is None:
        return _Followed(now, None, None, (), False)
    account = await get_directory().find_by_discord(discord_id)
    if account is None or account.suspended:
        return _Followed(now, None, None, (), False)
    return _Followed(now, account.account_id, account.username, account.discord_ids, False)


async def _refresh(info: SessionInfo, previous: _Followed | None, now: float) -> _Followed:
    """向 auth server 重新確認並記下結果；帳號有變就寫回資料庫，失效就刪除 session。不 raise DirectoryUnavailable。"""
    global _unavailable_until
    try:
        result = await _check(info, now)
    except DirectoryUnavailable:
        _unavailable_until = now + FOLLOW_INTERVAL
        result = _fallback(info, previous, now)
    if result.revoked:
        await run_db(lambda: _delete_session(info.session_id))
        return result
    if result.account_id != info.account_id:
        await run_db(lambda: _save_account_id(info.session_id, result.account_id))
    if _inflight.get(info.session_id) is asyncio.current_task():
        _followed[info.session_id] = result
    return result


async def _refresh_once(info: SessionInfo, previous: _Followed | None, now: float) -> _Followed:
    task = _inflight.get(info.session_id)
    if task is None:
        task = asyncio.ensure_future(_refresh(info, previous, now))
        _inflight[info.session_id] = task
        task.add_done_callback(
            lambda t: _inflight.pop(info.session_id) if _inflight.get(info.session_id) is t else None
        )
    # shield：一個請求被取消時，不連帶取消其他請求共用的確認
    return await asyncio.shield(task)


async def follow_account[S: SessionInfo](info: S, *, force: bool = False) -> S:
    """補上 session 的析域帳號；距上次確認超過 60 秒（或 force）才向 auth server 重新確認。Twitch 登入的 session 不跟隨，原樣回傳。

    Raises:
        DashboardError: 401 session_expired，析域登入的 session 已失效（已刪除）。
    """
    if info.login_method == "twitch":
        return info
    now = time.monotonic()
    previous = _followed.get(info.session_id)
    if previous is not None and not force and now - previous.checked_at < FOLLOW_INTERVAL:
        result = previous
    elif now < _unavailable_until:
        result = _fallback(info, previous, now)
        _followed[info.session_id] = result
    else:
        result = await _refresh_once(info, previous, now)
    if result.revoked:
        raise DashboardError(401, "session_expired")
    return dataclasses.replace(
        info,
        account_id=result.account_id,
        account_username=result.account_username,
        discord_ids=result.discord_ids,
        stale=result.stale,
    )


async def require_any_session(request: Request) -> SessionInfo:
    """驗證 session 的 dependency（Discord 或 Twitch 身分皆可），並補上帳號跟隨的結果。

    續期用的 Set-Cookie 不在這裡設：端點拋例外時 exception handler 會產生新的 response，這裡設的 cookie 會遺失。
    只在 request.state 記下，由 session_cookie_middleware 在回應出去時統一補。

    Raises:
        DashboardError: 401 session_expired。
    """
    session_id = request.cookies.get(SESSION_COOKIE)
    info = await run_db(lambda: _touch(session_id)) if session_id else None
    if info is None:
        if session_id:
            _followed.pop(session_id, None)
        request.state.dashboard_clear_cookie = True
        raise DashboardError(401, "session_expired")
    request.state.dashboard_renew_session = info.session_id
    try:
        info = await follow_account(info)
    except DashboardError:
        request.state.dashboard_clear_cookie = True
        raise
    if info.discord_user_id is not None:
        await _record_activity(int(info.discord_user_id))
    return info


async def require_session(request: Request) -> DiscordSessionInfo:
    """伺服器與個人區端點用的 dependency：只放行有 Discord 身分的 session。

    Raises:
        DashboardError: 401 session_expired；403 discord_required（沒有 Discord 身分）。
    """
    info = await require_any_session(request)
    if not isinstance(info, DiscordSessionInfo):
        raise DashboardError(403, "discord_required")
    return info


async def _record_activity(discord_id: int) -> None:
    """記下這個 Discord 本週有使用網站（T-10 連結率統計）；記錄失敗不影響請求。"""
    if not website_stats.needs_recording(discord_id):
        return
    try:
        await run_db(lambda: website_stats.record_activity(discord_id))
    except Exception:
        log.exception("record website activity failed")


async def session_cookie_middleware(request: Request, call_next):
    response = await call_next(request)
    if getattr(request.state, "dashboard_clear_cookie", False):
        delete_session_cookie(response)
    elif (session_id := getattr(request.state, "dashboard_renew_session", None)) is not None:
        set_session_cookie(response, session_id)
    return response
