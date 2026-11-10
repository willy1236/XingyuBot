"""訊息內容的 API 輸入驗證：把 starlib.message_content.validate 的錯誤轉成 400。"""

from starlib.message_content import MessageContent, validate

from .errors import DashboardError


def ensure_valid_message(c: MessageContent) -> None:
    """內容不合 Discord 上限或為空時拋 400 invalid_request，fields 列出每個錯誤欄位的 path 與原因。"""
    errors = validate(c)
    if errors:
        raise DashboardError(400, "invalid_request", fields=[e.model_dump() for e in errors])
