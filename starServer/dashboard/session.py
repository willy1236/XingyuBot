"""後台 session：30 天滑動，存在 DashboardSession。"""

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi.requests import Request
from sqlalchemy import delete

from starlib import sqldb
from starlib.database import DashboardSession
from starlib.utils import nowtz

from .db import run_db
from .errors import DashboardError

SESSION_COOKIE = "dashboard_session"
SESSION_TTL = timedelta(days=30)


@dataclass(frozen=True)
class SessionInfo:
    session_id: str
    discord_user_id: str
    name: str
    avatar: str | None


def _now() -> datetime:
    return nowtz()


def set_session_cookie(response, session_id: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, session_id, max_age=int(SESSION_TTL.total_seconds()), httponly=True, secure=True, samesite="lax"
    )


def delete_session_cookie(response) -> None:
    response.delete_cookie(SESSION_COOKIE, httponly=True, secure=True, samesite="lax")


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
    return SessionInfo(row.session_id, row.discord_user_id, row.name, row.avatar)


def create_session(discord_user_id: str, name: str, avatar: str | None, replace_session_id: str | None = None) -> str:
    """建立新 session。cookie 帶著的舊 session（不論是不是同一個帳號）一併刪掉，換帳號時就不會留著舊帳號的 session。"""
    s = sqldb.session
    if replace_session_id:
        s.execute(delete(DashboardSession).where(DashboardSession.session_id == replace_session_id))  # pyright: ignore[reportArgumentType]
    session_id = secrets.token_urlsafe(32)
    s.add(DashboardSession(session_id=session_id, discord_user_id=discord_user_id, name=name, avatar=avatar))
    s.commit()
    return session_id


def delete_user_sessions(discord_user_id: str) -> None:
    s = sqldb.session
    s.execute(delete(DashboardSession).where(DashboardSession.discord_user_id == discord_user_id))  # pyright: ignore[reportArgumentType]
    s.commit()


async def require_session(request: Request) -> SessionInfo:
    """驗證 session 的 dependency。

    續期用的 Set-Cookie 不在這裡設：端點拋例外時 exception handler 會產生新的 response，這裡設的 cookie 會遺失。
    只在 request.state 記下，由 session_cookie_middleware 在回應出去時統一補。
    """
    session_id = request.cookies.get(SESSION_COOKIE)
    info = await run_db(lambda: _touch(session_id)) if session_id else None
    if info is None:
        request.state.dashboard_clear_cookie = True
        raise DashboardError(401, "session_expired")
    request.state.dashboard_renew_session = info.session_id
    return info


async def session_cookie_middleware(request: Request, call_next):
    response = await call_next(request)
    if getattr(request.state, "dashboard_clear_cookie", False):
        delete_session_cookie(response)
    elif (session_id := getattr(request.state, "dashboard_renew_session", None)) is not None:
        set_session_cookie(response, session_id)
    return response
