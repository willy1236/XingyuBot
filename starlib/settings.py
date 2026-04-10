import os
from datetime import timedelta, timezone
from functools import lru_cache
from pathlib import Path

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

tz = timezone(timedelta(hours=8))

class AppSettings(BaseSettings):
    APP_ENV: str = "development"

    DB_HOST: str
    DB_PORT: int
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str

    MC_SERVER_HOST: str
    MC_SERVER_PORT: int
    MC_SERVER_PASSWORD: str

    JWT_SECRET: str

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


def get_required_env(key: str) -> str:
    settings = get_settings()
    if hasattr(settings, key):
        value = getattr(settings, key)
        text = str(value).strip()
    else:
        raw = os.getenv(key, "")
        text = raw.strip()

    if not text:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return text


def get_required_sql_env() -> dict[str, str | int]:
    settings = get_settings()

    return {
        "host": settings.DB_HOST,
        "port": settings.DB_PORT,
        "user": settings.DB_USER,
        "password": settings.DB_PASSWORD,
        "database": settings.DB_NAME,
    }


def get_required_mc_server_env() -> dict[str, str | int]:
    settings = get_settings()

    return {
        "host": settings.MC_SERVER_HOST,
        "port": settings.MC_SERVER_PORT,
        "password": settings.MC_SERVER_PASSWORD,
    }
