"""後台設定的讀取點；測試用 monkeypatch 換掉這裡的函式即可。"""

from starlib.settings import get_settings

DISCORD_OAUTH_SEQ = 4
#: Twitch 登入與啟用用的 OAuth client（與 Twitch bot 用的是同一個 Twitch 應用程式，另一筆設定）
TWITCH_OAUTH_SEQ = 3


def frontend_url() -> str:
    return (get_settings().DASHBOARD_FRONTEND_URL or "").rstrip("/")


def allowed_origins() -> list[str]:
    return list(get_settings().DASHBOARD_ALLOWED_ORIGINS)


def oidc_settings():
    """析域登入的 OIDC client 設定：(issuer, client_id, client_secret, redirect_uri)。"""
    s = get_settings()
    return (
        s.DASHBOARD_OIDC_ISSUER.rstrip("/"),
        s.DASHBOARD_OIDC_CLIENT_ID,
        s.DASHBOARD_OIDC_CLIENT_SECRET,
        s.DASHBOARD_OIDC_REDIRECT_URI,
    )


def main_guild_id() -> int | None:
    """主伺服器（`HAPPYCAMP_GUILD` 的第一個）；沒有設定時為 None。"""
    guilds = get_settings().HAPPYCAMP_GUILD
    return guilds[0] if guilds else None
