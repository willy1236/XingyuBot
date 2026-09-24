import asyncio
import logging
import os
import re
from collections.abc import Mapping
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

try:
    import sentry_sdk
    from sentry_sdk.integrations.asyncio import AsyncioIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    from sentry_sdk.integrations.threading import ThreadingIntegration
except ImportError:  # pragma: no cover - fallback for environments without sentry-sdk installed
    sentry_sdk = None

    class LoggingIntegration:  # type: ignore[override]
        def __init__(self, *args, **kwargs):
            del args, kwargs

    class AsyncioIntegration:  # type: ignore[override]
        pass

    class SqlalchemyIntegration:  # type: ignore[override]
        pass

    class ThreadingIntegration:  # type: ignore[override]
        pass


_SCRUB_KEYS = {
    "authorization",
    "cookie",
    "set-cookie",
    "access_token",
    "refresh_token",
    "jwt",
    "password",
    "passwd",
    "secret",
    "api_key",
}

_SCRUB_SUBSTRINGS = ("token", "secret", "password", "passwd", "api_key", "apikey", "api-key", "auth", "dsn")

# 指令列帶入的金鑰參數（如 rettiwt -k "<key>"），會出現在區域變數與 subprocess breadcrumbs 中
_SECRET_ARG_PATTERN = re.compile(r"""((?:^|\s)(?:-k|--key|--api-key)\s+)("[^"]*"|'[^']*'|\S+)""")

# 只截斷使用者附加資料中的長文字（如 Discord 訊息內容），不動事件本身的錯誤訊息與 breadcrumbs
_TRUNCATE_SECTIONS = {"extra"}

_SENTRY_INITIALIZED = False


def _project_root() -> Path:
    return Path(__file__).resolve().parent


def _resolve_env_file() -> Path | None:
    app_env = os.getenv("APP_ENV", "development").strip()
    env_file = _project_root() / f".env.{app_env}"
    if env_file.exists():
        return env_file

    fallback_file = _project_root() / ".env"
    if fallback_file.exists():
        return fallback_file

    return None


def _load_env_map() -> dict[str, str]:
    env_file = _resolve_env_file()
    if env_file is None:
        return {}

    data = dotenv_values(env_file)
    return {str(k): str(v) for k, v in data.items() if k and v is not None}


def _read_setting(key: str, default: str | None = None) -> str | None:
    if key in os.environ:
        return os.environ[key]

    return _load_env_map().get(key, default)


def _read_bool(key: str, default: bool) -> bool:
    value = _read_setting(key)
    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


def _read_float(key: str, default: float) -> float:
    value = _read_setting(key)
    if value is None:
        return default

    try:
        return float(value)
    except ValueError:
        return default


def _is_sensitive_key(key: str) -> bool:
    key_lower = key.lower()
    return key_lower in _SCRUB_KEYS or any(part in key_lower for part in _SCRUB_SUBSTRINGS)


def _sanitize_data(data: Any, *, truncate: bool = False) -> Any:
    if isinstance(data, Mapping):
        sanitized: dict[str, Any] = {}
        for k, v in data.items():
            key = str(k)
            if _is_sensitive_key(key):
                sanitized[key] = "[Filtered]"
            elif truncate and key in {"content", "message", "text"} and isinstance(v, str):
                sanitized[key] = v[:120]
            else:
                sanitized[key] = _sanitize_data(v, truncate=truncate or key in _TRUNCATE_SECTIONS)
        return sanitized

    if isinstance(data, str):
        return _SECRET_ARG_PATTERN.sub(r"\1[Filtered]", data)

    if isinstance(data, list):
        return [_sanitize_data(item, truncate=truncate) for item in data]

    if isinstance(data, tuple):
        return tuple(_sanitize_data(item, truncate=truncate) for item in data)

    return data


def _resolve_release() -> str | None:
    try:
        return version("xingyubot")
    except PackageNotFoundError:
        return None


_CAPTURED_ATTR = "_xingyu_sentry_captured"


def _exception_of(hint: dict[str, Any]) -> BaseException | None:
    exc_info = hint.get("exc_info")
    if not exc_info:
        record = hint.get("log_record")
        exc_info = getattr(record, "exc_info", None) if record is not None else None
    return exc_info[1] if exc_info else None


def _already_captured(hint: dict[str, Any]) -> bool:
    exc = _exception_of(hint)
    return exc is not None and getattr(exc, _CAPTURED_ATTR, False)


def before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    # 同一個例外已經由 capture_exception_safe 回報過，後續的 log.exception / 執行緒整合等重複事件直接丟棄
    if _already_captured(hint):
        return None
    # 任務在關機或重啟時被取消屬正常流程，apscheduler 會把 CancelledError 記成 error
    if isinstance(_exception_of(hint), asyncio.CancelledError):
        return None
    return _sanitize_data(event)


def init_sentry(service: str = "xingyubot") -> bool:
    global _SENTRY_INITIALIZED

    if _SENTRY_INITIALIZED:
        return True

    if sentry_sdk is None:
        return False

    sentry_enabled = _read_bool("SENTRY_ENABLED", False)
    sentry_dsn = _read_setting("SENTRY_DSN")
    if not sentry_enabled or not sentry_dsn:
        return False

    release = _read_setting("SENTRY_RELEASE") or _resolve_release()

    sentry_sdk.init(
        dsn=sentry_dsn,
        environment=_read_setting("SENTRY_ENVIRONMENT") or os.getenv("APP_ENV", "development"),
        release=release,
        debug=_read_bool("SENTRY_DEBUG", False),
        send_default_pii=_read_bool("SENTRY_SEND_DEFAULT_PII", False),
        traces_sample_rate=_read_float("SENTRY_TRACES_SAMPLE_RATE", 0.0),
        before_send=before_send,
        integrations=[
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
            AsyncioIntegration(),
            ThreadingIntegration(),
            SqlalchemyIntegration(),
        ],
    )

    sentry_sdk.set_tag("service", service)
    _SENTRY_INITIALIZED = True
    return True


def capture_exception_safe(exc: Exception, *, tags: dict[str, str] | None = None, extras: dict[str, Any] | None = None) -> None:
    """帶 tags/extras 回報例外到 Sentry，每個例外只會回報一次。

    專案慣例：
    - 不需要 tags 時，直接 log.exception(...) / log.error(..., exc_info=e)，由 LoggingIntegration 回報。
    - 需要 tags 時呼叫本函式，之後本地 log 一律帶 exc_info（同一例外的後續事件會在 before_send 被丟棄）。
    - 不要用 log.error(f"...{e}") 記錄例外：沒有 exc_info 會變成另一筆無堆疊的訊息事件。
    """
    if sentry_sdk is None:
        return
    if getattr(exc, _CAPTURED_ATTR, False):
        return

    if tags or extras:
        with sentry_sdk.new_scope() as scope:
            for key, value in (tags or {}).items():
                scope.set_tag(key, value)
            for key, value in (extras or {}).items():
                if _is_sensitive_key(key):
                    scope.set_extra(key, "[Filtered]")
                else:
                    scope.set_extra(key, _sanitize_data(value, truncate=True))
            sentry_sdk.capture_exception(exc)
    else:
        sentry_sdk.capture_exception(exc)
    _mark_captured(exc)


def _mark_captured(exc: BaseException) -> None:
    try:
        setattr(exc, _CAPTURED_ATTR, True)
    except (AttributeError, TypeError):
        pass
