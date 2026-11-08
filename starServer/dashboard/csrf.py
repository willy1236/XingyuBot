"""CSRF：memory.、cup.、forgejo.domalyze.net 等子網域跟後台同 site，SameSite=Lax 擋不住它們。
/dashboard/* 的非 GET 請求一律檢查 Origin；有 body 的要求 Content-Type: application/json。
失敗回 400 invalid_request（不用 no_permission，以免前端 wrapper 誤清表單暫存）。
"""

from fastapi.requests import Request

from . import config
from .errors import error_response

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _has_body(request: Request) -> bool:
    length = request.headers.get("content-length")
    if length is not None:
        return length.strip() not in ("", "0")
    return "transfer-encoding" in request.headers


async def csrf_middleware(request: Request, call_next):
    path = request.url.path
    if (path == "/dashboard" or path.startswith("/dashboard/")) and request.method not in SAFE_METHODS:
        if request.headers.get("origin") not in config.allowed_origins():
            return error_response(400, "invalid_request")
        if _has_body(request):
            content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
            if content_type != "application/json":
                return error_response(400, "invalid_request")
    return await call_next(request)
