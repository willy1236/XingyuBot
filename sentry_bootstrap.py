import logging
import os
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
    return key_lower in _SCRUB_KEYS or "token" in key_lower


def _sanitize_data(data: Any) -> Any:
    if isinstance(data, Mapping):
        sanitized: dict[str, Any] = {}
        for k, v in data.items():
            key = str(k)
            if _is_sensitive_key(key):
                sanitized[key] = "[Filtered]"
            elif key in {"content", "message", "text"} and isinstance(v, str):
                sanitized[key] = v[:120]
            else:
                sanitized[key] = _sanitize_data(v)
        return sanitized

    if isinstance(data, list):
        return [_sanitize_data(item) for item in data]

    if isinstance(data, tuple):
        return tuple(_sanitize_data(item) for item in data)

    return data


def _resolve_release() -> str | None:
    try:
        return version("xingyubot")
    except PackageNotFoundError:
        return None


def before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    del hint
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
    if sentry_sdk is None:
        return

    if tags or extras:
        with sentry_sdk.push_scope() as scope:
            for key, value in (tags or {}).items():
                scope.set_tag(key, value)
            for key, value in (extras or {}).items():
                if _is_sensitive_key(key):
                    scope.set_extra(key, "[Filtered]")
                else:
                    scope.set_extra(key, _sanitize_data(value))
            sentry_sdk.capture_exception(exc)
        return

    sentry_sdk.capture_exception(exc)
