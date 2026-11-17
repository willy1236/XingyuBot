"""析域登入：以 auth server（Hydra）的 OIDC 登入，進入域民連結的其中一個 Discord。

流程：/to/dashboard-domalyze-login 寫 dashboard_oidc cookie（state、PKCE verifier、next、origin）並導向 auth server，
完成後回到 /oauth/domalyze。域民只連結一個 Discord 時直接建立 session；連結多個時把候選存在記憶體、設 dashboard_pick cookie，
導向前端的選擇畫面，由 /dashboard/login/candidates 與 /dashboard/login/select 完成。
失敗一律導回前端的登入頁，以 notice 說明原因。
"""

import asyncio
import base64
import hmac
import json
import logging
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode
from uuid import UUID

from authlib.common.security import generate_token
from authlib.integrations.httpx_client import AsyncOAuth2Client
from fastapi import APIRouter
from fastapi.requests import Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel

from sentry_bootstrap import capture_exception_safe
from starlib.identity import Account, DirectoryUnavailable
from starlib.identity.resolver import get_directory

from . import config
from .auth import avatar_url, sanitize_next, sanitize_origin
from .db import run_db
from .discord_users import fetch_discord_user
from .errors import DashboardError
from .session import SESSION_COOKIE, create_session, remember_account, set_session_cookie

log = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard")
to_router = APIRouter()

OIDC_COOKIE = "dashboard_oidc"
PICK_COOKIE = "dashboard_pick"
#: 登入流程與選擇畫面的有效時間（秒）
FLOW_MAX_AGE = 600
SCOPE = "openid profile"
HTTP_TIMEOUT = 5.0
#: 測試用：換成 authlib 所用 HTTP 函式庫的 MockTransport，就不必連到真的 auth server
_http_transport = None


# ====== 導回登入頁 ======
def _login_page(origin: str, notice: str, next: str | None = None) -> RedirectResponse:
    query = {"notice": notice}
    if next:
        query["next"] = next
    return RedirectResponse(url=f"{origin}/dashboard-login?{urlencode(query)}")


def _set_cookie(response: Response, name: str, value: str) -> None:
    response.set_cookie(name, value, max_age=FLOW_MAX_AGE, httponly=True, secure=True, samesite="lax")


def _delete_cookie(response: Response, name: str) -> None:
    response.delete_cookie(name, httponly=True, secure=True, samesite="lax")


# ====== dashboard_oidc cookie ======
class OidcCookie(BaseModel):
    state: str
    verifier: str
    next: str = "/dashboard"
    origin: str = ""


def _encode(cookie: OidcCookie) -> str:
    return base64.urlsafe_b64encode(cookie.model_dump_json().encode()).decode()


def _decode(raw: str | None) -> OidcCookie | None:
    if raw is None:
        return None
    try:
        cookie = OidcCookie(**json.loads(base64.urlsafe_b64decode(raw.encode())))
    except Exception:
        return None
    # cookie 沒有簽章，同 site 的子網域可以寫入，讀出後用同一套規則再驗一次
    cookie.next = sanitize_next(cookie.next)
    cookie.origin = sanitize_origin(cookie.origin)
    return cookie


# ====== OIDC ======
_discovery: dict | None = None


async def _fetch_discovery(issuer: str) -> dict:
    async with _oauth_client() as client:
        resp = await client.request("GET", f"{issuer}/.well-known/openid-configuration", withhold_token=True)
        resp.raise_for_status()
        data = resp.json()
    for key in ("authorization_endpoint", "token_endpoint", "userinfo_endpoint"):
        if not isinstance(data.get(key), str):
            raise ValueError(f"discovery 缺少 {key}")
    return data


async def _get_discovery() -> dict:
    """auth server 的 OIDC discovery；成功後快取，失敗不快取。"""
    global _discovery
    if _discovery is None:
        issuer, *_ = config.oidc_settings()
        _discovery = await _fetch_discovery(issuer)
    return _discovery


def _oauth_client() -> AsyncOAuth2Client:
    _, client_id, client_secret, redirect_uri = config.oidc_settings()
    return AsyncOAuth2Client(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=SCOPE,
        code_challenge_method="S256",
        token_endpoint_auth_method="client_secret_basic",
        timeout=HTTP_TIMEOUT,
        transport=_http_transport,
    )


async def _account_id_from_code(code: str, verifier: str) -> UUID:
    """以授權碼換 token，從 userinfo 取得 sub（first-party client 的 sub 就是 account_id）。"""
    discovery = await _get_discovery()
    async with _oauth_client() as client:
        await client.fetch_token(discovery["token_endpoint"], code=code, code_verifier=verifier)
        resp = await client.get(discovery["userinfo_endpoint"])
        resp.raise_for_status()
        return UUID(resp.json()["sub"])


# ====== Discord 名稱與頭像 ======
@dataclass(frozen=True)
class Candidate:
    discord_id: int
    #: 取不到 Discord 使用者時為 None
    name: str | None
    avatar: str | None

    @property
    def session_name(self) -> str:
        return self.name or str(self.discord_id)

    def to_json(self) -> dict:
        found = self.name is not None
        return {
            "id": str(self.discord_id),
            "name": self.session_name,
            "avatar_url": avatar_url(str(self.discord_id), self.avatar) if found else None,
        }


async def _candidate(discord_id: int) -> Candidate:
    profile = await fetch_discord_user(discord_id)
    return Candidate(discord_id, None, None) if profile is None else Candidate(discord_id, profile.name, profile.avatar)


# ====== 待選資料 ======
@dataclass(frozen=True)
class _Pending:
    expires_at: float
    account: Account
    candidates: tuple[Candidate, ...]
    next: str
    origin: str
    old_session_id: str | None


# dashboard_pick cookie 的值 -> 待選資料；只在記憶體，服務重啟後失效
_pending: dict[str, _Pending] = {}


def _prune_pending() -> None:
    now = time.monotonic()
    for key in [k for k, v in _pending.items() if v.expires_at <= now]:
        del _pending[key]


def _get_pending(request: Request) -> tuple[str, _Pending]:
    key = request.cookies.get(PICK_COOKIE)
    pending = _pending.get(key) if key else None
    if key is None or pending is None or pending.expires_at <= time.monotonic():
        raise DashboardError(401, "pick_expired")
    return key, pending


async def _start_session(account: Account, candidate: Candidate, old_session_id: str | None) -> str:
    session_id = await run_db(
        lambda: create_session(
            str(candidate.discord_id),
            candidate.session_name,
            candidate.avatar,
            old_session_id,
            account_id=account.account_id,
            via_domalyze=True,
        )
    )
    remember_account(session_id, account)
    log.info("Dashboard domalyze login: account %s discord %s", account.account_id, candidate.discord_id)
    return session_id


# ====== 登入入口 ======
@to_router.get("/to/dashboard-domalyze-login")
async def to_dashboard_domalyze_login(next: str | None = None, origin: str | None = None):
    next, origin = sanitize_next(next), sanitize_origin(origin)
    try:
        discovery = await _get_discovery()
    except Exception as exc:
        log.warning("Domalyze login: discovery failed: %r", exc)
        return _login_page(origin, "domalyze_unavailable", next)

    verifier = generate_token(48)
    async with _oauth_client() as client:
        url, state = client.create_authorization_url(discovery["authorization_endpoint"], code_verifier=verifier)
    response = RedirectResponse(url=url)
    _set_cookie(response, OIDC_COOKIE, _encode(OidcCookie(state=state, verifier=verifier, next=next, origin=origin)))
    return response


@to_router.get("/oauth/domalyze")
async def oauth_domalyze(request: Request):
    cookie = _decode(request.cookies.get(OIDC_COOKIE))
    response = await _handle_callback(request, cookie)
    _delete_cookie(response, OIDC_COOKIE)
    return response


async def _handle_callback(request: Request, cookie: OidcCookie | None) -> Response:
    params = request.query_params
    state = params.get("state")
    if cookie is None or state is None or not hmac.compare_digest(cookie.state.encode(), state.encode()):
        return _login_page(
            config.frontend_url() if cookie is None else cookie.origin,
            "domalyze_expired",
            None if cookie is None else cookie.next,
        )
    origin, next = cookie.origin, cookie.next

    code = params.get("code")
    if params.get("error") == "access_denied":
        return _login_page(origin, "domalyze_denied", next)
    if params.get("error") or not code:
        return _login_page(origin, "domalyze_unavailable", next)

    try:
        account_id = await _account_id_from_code(code, cookie.verifier)
        resolved = await get_directory().find_by_account_id(account_id)
    except DirectoryUnavailable:
        return _login_page(origin, "domalyze_unavailable", next)
    except Exception as exc:
        capture_exception_safe(exc, tags={"service": "website", "source": "dashboard_domalyze_login"})
        log.exception("Dashboard domalyze login failed: %s", exc)
        return _login_page(origin, "domalyze_unavailable", next)

    account = None if resolved is None else resolved.account
    if account is None or account.suspended:
        return _login_page(origin, "domalyze_denied", next)
    if not account.discord_ids:
        return _login_page(origin, "domalyze_no_discord", next)

    old_session_id = request.cookies.get(SESSION_COOKIE)
    candidates = tuple(await asyncio.gather(*(_candidate(i) for i in account.discord_ids)))
    if len(candidates) == 1:
        session_id = await _start_session(account, candidates[0], old_session_id)
        response = RedirectResponse(url=f"{origin}{next}")
        set_session_cookie(response, session_id)
        return response

    _prune_pending()
    key = secrets.token_urlsafe(32)
    _pending[key] = _Pending(time.monotonic() + FLOW_MAX_AGE, account, candidates, next, origin, old_session_id)
    response = RedirectResponse(url=f"{origin}/dashboard-login/select?{urlencode({'next': next})}")
    _set_cookie(response, PICK_COOKIE, key)
    return response


# ====== 選擇畫面 ======
@router.get("/login/candidates")
async def login_candidates(request: Request):
    _, pending = _get_pending(request)
    return {"candidates": [c.to_json() for c in pending.candidates]}


class SelectBody(BaseModel):
    discord_user_id: str


@router.post("/login/select")
async def login_select(request: Request, body: SelectBody):
    key, pending = _get_pending(request)
    candidate = next((c for c in pending.candidates if str(c.discord_id) == body.discord_user_id), None)
    if candidate is None:
        raise DashboardError(400, "invalid_candidate")

    session_id = await _start_session(pending.account, candidate, pending.old_session_id)
    _pending.pop(key, None)
    response = JSONResponse({"redirect": f"{pending.origin}{pending.next}"})
    set_session_cookie(response, session_id)
    _delete_cookie(response, PICK_COOKIE)
    return response
