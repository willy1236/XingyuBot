"""後台設定的讀取點；測試用 monkeypatch 換掉這兩個函式即可。"""

from starlib.settings import get_settings

DISCORD_OAUTH_SEQ = 4


def frontend_url() -> str:
    return (get_settings().DASHBOARD_FRONTEND_URL or "").rstrip("/")


def allowed_origins() -> list[str]:
    return list(get_settings().DASHBOARD_ALLOWED_ORIGINS)
