"""實況主 Twitch token（OAuth client #3）的取得與續期。web 與 Twitch bot 兩個 process 都只經這裡取 token。

Twitch 換新 token 時舊的 refresh token 立刻失效，所以兩個 process 同時續期會讓後到的那個失敗。
續期時用 PostgreSQL 的 SELECT ... FOR UPDATE 鎖住那筆 token，拿到鎖後重查有效期，已被別人換新就直接用。
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import httpx
from sqlmodel import select

from starlib.database import APIType, OAuthToken, sqldb
from starlib.oauth.twitch_oauth import TwitchOAuth

log = logging.getLogger(__name__)

# 實況主授權用的 OAuth client（bot 自己用的是 #2）
BROADCASTER_CLIENT_SEQ = 3
# access token 剩不到這段時間就續期
REFRESH_MARGIN = timedelta(minutes=10)
REQUEST_TIMEOUT = 5.0


@dataclass(frozen=True, slots=True)
class TokenInvalid:
    """拿不到可用的 token。missing：沒有授權過；revoked：refresh token 已失效，要實況主重新授權；
    unavailable：Twitch 暫時無法回應，授權本身可能仍然有效。"""

    reason: Literal["missing", "revoked", "unavailable"]


async def broadcaster_token(twitch_id: int) -> str | TokenInvalid:
    """回傳實況主可用的 access token；快過期（10 分鐘內）時先用 refresh token 換新並寫回 DB。不 raise。

    DB 與續期的同步工作丟到 asyncio 預設 executor，給 Twitch bot 用。web 端有自己限制連線數的 executor，
    要用 `starServer.dashboard.twitch_control.broadcaster_token`，它經 `run_db` 呼叫 `broadcaster_token_blocking`。
    """
    return await asyncio.to_thread(broadcaster_token_blocking, twitch_id)


def broadcaster_token_blocking(twitch_id: int) -> str | TokenInvalid:
    """`broadcaster_token` 的同步版：會讀寫 DB、續期時最多等 Twitch 5 秒，要在 worker thread 上呼叫。不 raise。"""
    try:
        return _broadcaster_token(twitch_id)
    except Exception:
        log.exception("取得實況主 %s 的 token 失敗", twitch_id)
        return TokenInvalid("unavailable")


def _fresh(token: OAuthToken, now: datetime) -> bool:
    return token.expires_at is not None and token.expires_at - now > REFRESH_MARGIN


def _broadcaster_token(twitch_id: int) -> str | TokenInvalid:
    # 在 to_thread 的 worker thread 上執行：用完要釋放該 thread 的 session，不讓交易一直停著
    try:
        client = sqldb.get_oauth_client(APIType.Twitch, BROADCASTER_CLIENT_SEQ)
        user_id = str(twitch_id)
        token = sqldb.get_oauth_token(user_id, client.credential_id)
        if token is None or not token.refresh_token:
            return TokenInvalid("missing")
        if _fresh(token, datetime.now(UTC)):
            return token.access_token
        return _refresh_locked(client.credential_id, user_id, client.client_id, client.client_secret)
    finally:
        sqldb.release_session()


def _refresh_locked(credential_id: int, user_id: str, client_id: str, client_secret: str) -> str | TokenInvalid:
    session = sqldb.session
    stmt = (
        select(OAuthToken)
        .where(OAuthToken.client_credential_id == credential_id, OAuthToken.user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    try:
        token = session.exec(stmt).one_or_none()
        if token is None or not token.refresh_token:
            session.rollback()
            return TokenInvalid("missing")
        now = datetime.now(UTC)
        if _fresh(token, now):
            # 等鎖的期間別人已經換新
            access_token = token.access_token
            session.rollback()
            return access_token

        try:
            response = httpx.post(
                TwitchOAuth.token_url,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": token.refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                timeout=REQUEST_TIMEOUT,
            )
        except httpx.HTTPError as exc:
            log.warning("續期 %s 的 token 時連不上 Twitch：%r", user_id, exc)
            return _unavailable(session, token, now)
        if response.status_code in (400, 401):
            log.warning("%s 的 refresh token 已失效：%s", user_id, response.text)
            session.rollback()
            return TokenInvalid("revoked")
        if response.status_code != 200:
            log.warning("續期 %s 的 token 失敗：%s %s", user_id, response.status_code, response.text)
            return _unavailable(session, token, now)

        data = response.json()
        token.access_token = data["access_token"]
        token.refresh_token = data.get("refresh_token", token.refresh_token)
        token.expires_at = now + timedelta(seconds=data.get("expires_in", 0))
        if scope := data.get("scope"):
            token.scope = scope if isinstance(scope, list) else scope.split(" ")
        session.add(token)
        session.commit()
        return token.access_token
    except Exception:
        session.rollback()
        raise


def _unavailable(session, token: OAuthToken, now: datetime) -> str | TokenInvalid:
    """Twitch 暫時無法回應：舊的 access token 還沒過期就繼續用，過期了才算拿不到。"""
    access_token, expires_at = token.access_token, token.expires_at
    session.rollback()
    if expires_at is not None and expires_at > now:
        return access_token
    return TokenInvalid("unavailable")
