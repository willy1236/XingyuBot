"""伺服器管理後台的 API。

各卡的端點放在這個 package 的各自模組，模組用固定名稱暴露 router：
`router` 帶 `/dashboard` 前綴，`to_router` 不帶前綴、放 `/to/*`；兩個都可有可無。
install() 會自動掃描並掛上，新增模組不必改這個檔或 bot_website.py。
"""

import importlib
import pkgutil

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from . import config
from .csrf import csrf_middleware
from .errors import install_error_handlers
from .session import session_cookie_middleware


def install(app: FastAPI) -> None:
    """掛上後台的 handler、middleware 與 router。

    必須在其他 middleware（例如 sentry_exception_middleware）之後呼叫：CORS 最後加入才會在最外層，
    500 回應也帶得到 CORS header。
    """
    install_error_handlers(app)

    for module_info in pkgutil.iter_modules(__path__):
        if module_info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{__name__}.{module_info.name}")
        for attr in ("router", "to_router"):
            router = getattr(module, attr, None)
            if router is not None:
                app.include_router(router)

    # 後加入的在外層：session 補 cookie 在內，CSRF 其次，CORS 最外
    app.add_middleware(BaseHTTPMiddleware, dispatch=session_cookie_middleware)
    app.add_middleware(BaseHTTPMiddleware, dispatch=csrf_middleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.allowed_origins(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type"],
    )
