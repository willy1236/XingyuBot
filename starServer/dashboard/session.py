"""後台 session：30 天滑動，存在 DashboardSession；session 帶的析域帳號每 60 秒向 auth server 重新確認一次。

session 的身分一律是一個 Discord 帳號，析域帳號是附帶欄位。帳號跟隨的確認結果存在記憶體（以 session ID 為 key），
auth server 暫時不可用時沿用上次結果，重啟後則以資料庫的 account_id 為準。
"""

import dataclasses
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from fastapi.requests import Request
from sqlalchemy import delete, update

from starlib import sqldb
from starlib.database import DashboardSession
from starlib.identity import DirectoryUnavailable
from starlib.identity.resolver import get_directory
from starlib.utils import nowtz

from .db import run_db
from .errors import DashboardError

SESSION_COOKIE = "dashboard_session"
SESSION_TTL = timedelta(days=30)
#: 帳號跟隨的重新確認間隔，也是 auth server 不可用後暫停查詢的時間（秒）
FOLLOW_INTERVAL = 60.0


@dataclass(frozen=True)
class SessionInfo:
    session_id: str
    discord_user_id: str
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


def _now() -> datetime:
    return nowtz()


def set_session_cookie(response, session_id: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, session_id, max_age=int(SESSION_TTL.total_seconds()), httponly=True, secure=True, samesite="lax"
    )


def delete_session_cookie(response) -> None:
    response.delete_cookie(SESSION_COOKIE, httponly=True, secure=True, samesite="lax")


def _info(row: DashboardSession) -> SessionInfo:
    return SessionInfo(
        row.session_id,
        row.discord_user_id,
        row.name,
        row.avatar,
        account_id=row.account_id,
        via_domalyze=row.via_domalyze,
    )


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
    discord_user_id: str,
    name: str,
    avatar: str | None,
    replace_session_id: str | None = None,
    *,
    account_id: UUID | None = None,
    via_domalyze: bool = False,
) -> str:
    """建立新 session。cookie 帶著的舊 session（不論是不是同一個帳號）一併刪掉，換帳號時就不會留著舊帳號的 session。"""
    s = sqldb.session
    # 順手清掉已過期的 session，沒有人再用到的列才不會一直留在表裡
    s.execute(delete(DashboardSession).where(DashboardSession.last_used_at < _now() - SESSION_TTL))  # pyright: ignore[reportArgumentType]
    if replace_session_id:
        s.execute(delete(DashboardSession).where(DashboardSession.session_id == replace_session_id))  # pyright: ignore[reportArgumentType]
        _followed.pop(replace_session_id, None)
    session_id = secrets.token_urlsafe(32)
    s.add(
        DashboardSession(
            session_id=session_id,
            discord_user_id=discord_user_id,
            name=name,
            avatar=avatar,
            account_id=account_id,
            via_domalyze=via_domalyze,
        )
    )
    s.commit()
    return session_id


def delete_user_sessions(discord_user_id: str) -> None:
    s = sqldb.session
    s.execute(delete(DashboardSession).where(DashboardSession.discord_user_id == discord_user_id))  # pyright: ignore[reportArgumentType]
    s.commit()


# ====== 帳號跟隨 ======
@dataclass(frozen=True)
class _Followed:
    checked_at: float
    account_id: UUID | None
    account_username: str | None
    discord_ids: tuple[int, ...]
    stale: bool


# session ID -> 最近一次確認結果
_followed: dict[str, _Followed] = {}
# auth server 不可用後，這個時間點（monotonic）之前不再查詢
_unavailable_until = 0.0


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
    discord_ids = (int(info.discord_user_id),) if info.account_id is not None else ()
    return _Followed(now, info.account_id, None, discord_ids, True)


async def _check(info: SessionInfo, now: float) -> _Followed:
    """Discord 登入的 session：以這個 Discord 目前連結、未停權的域民為準（合併後就是存續帳號）。

    Raises:
        DirectoryUnavailable: auth server 沒給出明確答案。
    """
    account = await get_directory().find_by_discord(int(info.discord_user_id))
    if account is None or account.suspended:
        return _Followed(now, None, None, (), False)
    return _Followed(now, account.account_id, account.username, account.discord_ids, False)


async def follow_account(info: SessionInfo, *, force: bool = False) -> SessionInfo:
    """補上 session 的析域帳號；距上次確認超過 60 秒（或 force）才向 auth server 重新確認。不 raise。"""
    global _unavailable_until
    if info.via_domalyze:
        # 析域登入的 session 由 T-04 補上跟隨規則，先沿用資料庫的 account_id
        return info

    now = time.monotonic()
    previous = _followed.get(info.session_id)
    if previous is not None and not force and now - previous.checked_at < FOLLOW_INTERVAL:
        result = previous
    elif now < _unavailable_until:
        result = _fallback(info, previous, now)
    else:
        try:
            result = await _check(info, now)
        except DirectoryUnavailable:
            _unavailable_until = now + FOLLOW_INTERVAL
            result = _fallback(info, previous, now)
        if result.account_id != info.account_id:
            await run_db(lambda: _save_account_id(info.session_id, result.account_id))
    _followed[info.session_id] = result
    return dataclasses.replace(
        info,
        account_id=result.account_id,
        account_username=result.account_username,
        discord_ids=result.discord_ids,
        stale=result.stale,
    )


async def require_session(request: Request) -> SessionInfo:
    """驗證 session 的 dependency，並補上帳號跟隨的結果。

    續期用的 Set-Cookie 不在這裡設：端點拋例外時 exception handler 會產生新的 response，這裡設的 cookie 會遺失。
    只在 request.state 記下，由 session_cookie_middleware 在回應出去時統一補。
    """
    session_id = request.cookies.get(SESSION_COOKIE)
    info = await run_db(lambda: _touch(session_id)) if session_id else None
    if info is None:
        if session_id:
            _followed.pop(session_id, None)
        request.state.dashboard_clear_cookie = True
        raise DashboardError(401, "session_expired")
    request.state.dashboard_renew_session = info.session_id
    return await follow_account(info)


async def session_cookie_middleware(request: Request, call_next):
    response = await call_next(request)
    if getattr(request.state, "dashboard_clear_cookie", False):
        delete_session_cookie(response)
    elif (session_id := getattr(request.state, "dashboard_renew_session", None)) is not None:
        set_session_cookie(response, session_id)
    return response
