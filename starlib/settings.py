import os
from datetime import timedelta, timezone
from functools import lru_cache
from pathlib import Path

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

tz = timezone(timedelta(hours=8))

class AppSettings(BaseSettings):
    APP_ENV: str = "development"
    BOT_CODE: str

    LOG_LEVEL: str | int = "INFO"
    API_WEBSITE: bool = False
    FILE_LOG: bool = False
    MONGODB_CONNECTION: bool = False
    TWITCH_BOT: bool = False

    DB_HOST: str
    DB_PORT: int
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str

    MC_SERVER_HOST: str
    MC_SERVER_PORT: int
    MC_SERVER_PASSWORD: str

    ZEROTIER_NETWORK_ID: str
    BASE_DOMAIN: str
    BASE_WWW_URL: str

    TASK_REPORT: int
    FEEDBACK_CHANNEL: int
    ERROR_REPORT: int
    REPORT_CHANNEL: int
    DM_CHANNEL: int
    MENTIONED_CHANNEL: int
    MENTION_EVERYONE_CHANNEL: int
    VIP_ADMIN_CHANNEL: int

    HAPPYCAMP_GUILD: list[int] = Field(default_factory=list)
    DEBUG_GUILDS: list[int] = Field(default_factory=list)

    DEBUG_MODE: bool = True
    NOTION_DATABASE_ID: str

    JWT_SECRET: str

    SENTRY_ENABLED: bool = False
    SENTRY_DSN: str | None = None
    SENTRY_ENVIRONMENT: str | None = None
    SENTRY_RELEASE: str | None = None
    SENTRY_DEBUG: bool = False
    SENTRY_SEND_DEFAULT_PII: bool = False
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def _resolve_env_file() -> Path | None:
    """Resolve .env.{APP_ENV} first, fallback to .env."""
    project_root = Path(__file__).resolve().parent.parent
    app_env = os.getenv("APP_ENV", "development").strip()

    env_file = project_root / f".env.{app_env}"
    if env_file.exists():
        return env_file

    fallback_file = project_root / ".env"
    if fallback_file.exists():
        return fallback_file

    return None


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    env_file = _resolve_env_file()
    kwargs: dict[str, str] = {}
    if env_file is not None:
        kwargs["_env_file"] = str(env_file)

    try:
        return AppSettings(**kwargs)
    except ValidationError as exc:
        raise RuntimeError(f"Invalid environment settings: {exc}") from exc
