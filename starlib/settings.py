import os
import re
from datetime import timedelta, timezone
from functools import lru_cache
from pathlib import Path

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# 身分組代號規則（與 auth server 一致）
ROLE_CODE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
# 合法的權限等級數字，需與 PrivilegeLevel 一致；這裡不能 import enums（會經由 starlib.database 繞回 settings），由測試保證同步
VALID_PRIVILEGE_VALUES = frozenset({0, 1, 2, 3})


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

    ZEROTIER_NETWORK_ID: str
    NETBIRD_API_URL: str = "https://api.netbird.io"
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

    AUTH_INTERNAL_URL: str = "http://127.0.0.1:8002"
    AUTH_SERVICE_KEY: str
    IDENTITY_TTL_SECONDS: int = 3600
    # auth server 管理頁的 Twitch 登入方式代號（login_provider.slug）
    AUTH_TWITCH_PROVIDER: str = "twitch"
    # 身分組代號 -> PrivilegeLevel 數字，例如 {"some-role": 2}；沒設定時所有人都是一般使用者
    PRIVILEGE_ROLES: dict[str, int] = Field(default_factory=dict)

    SENTRY_ENABLED: bool = False
    SENTRY_DSN: str | None = None
    SENTRY_ENVIRONMENT: str | None = None
    SENTRY_RELEASE: str | None = None
    SENTRY_DEBUG: bool = False
    SENTRY_SEND_DEFAULT_PII: bool = False
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0

    @field_validator("PRIVILEGE_ROLES")
    @classmethod
    def _validate_privilege_roles(cls, value: dict[str, int]) -> dict[str, int]:
        for role, level in value.items():
            if not ROLE_CODE_PATTERN.fullmatch(role):
                raise ValueError(f"PRIVILEGE_ROLES 的身分組代號不合法：{role!r}")
            if level not in VALID_PRIVILEGE_VALUES:
                raise ValueError(f"PRIVILEGE_ROLES 的等級不合法：{role!r} -> {level!r}")
        return value

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
