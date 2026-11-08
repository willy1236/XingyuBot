"""後台所有錯誤回應的格式：{"error": <錯誤碼>, ...}。其他卡只 raise DashboardError，不改這個檔。"""

from fastapi import FastAPI
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.requests import Request
from fastapi.responses import JSONResponse


class DashboardError(Exception):
    def __init__(self, status: int, code: str, **extra):
        super().__init__(code)
        self.status = status
        self.code = code
        self.extra = extra


def error_response(status: int, code: str, **extra) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": code, **extra})


async def _dashboard_error_handler(request: Request, exc: DashboardError):
    return error_response(exc.status, exc.code, **exc.extra)


async def _validation_error_handler(request: Request, exc: RequestValidationError):
    # handler 掛在 app 層，只轉換後台的路徑；既有的 /youtube_push、/callback/* 維持 FastAPI 預設
    if request.url.path.startswith("/dashboard/"):
        return error_response(400, "invalid_request")
    return await request_validation_exception_handler(request, exc)


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DashboardError, _dashboard_error_handler)  # pyright: ignore[reportArgumentType]
    app.add_exception_handler(RequestValidationError, _validation_error_handler)  # pyright: ignore[reportArgumentType]
