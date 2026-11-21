"""後台測試與 E2E 共用、不依賴 pytest 的設定：換掉對外依賴、建立 session、假的 Discord 成員與伺服器。

pytest fixture（`dashboard_auth`、`dashboard_guilds`）與 E2E 啟動器（`e2e`）都從這裡呼叫。
替換一律經由呼叫端傳入的 `setattr(obj, name, value)`：測試傳 `monkeypatch.setattr`，E2E 傳 `Patches().setattr`。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from types import SimpleNamespace
from typing import Any

import discord as dpy

from starlib.database import DashboardSession
from starlib.identity import resolver as resolver_module
from starlib.utils import nowtz
from starServer.dashboard import auth, channel_mods, config, discord_users, session
from tests.helpers.identity import FakeDirectory

USER_ID = "111111111111111111"

#: 測試用的 bot 帳號 Twitch ID
BOT_TWITCH_ID = "9000"

SetAttr = Callable[[Any, str, Any], None]


class Patches:
    """pytest 之外的 monkeypatch：`setattr` 記下原值，`undo()` 還原。"""

    def __init__(self):
        self._undo: list[tuple[Any, str, Any]] = []

    def setattr(self, obj: Any, name: str, value: Any) -> None:
        self._undo.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def undo(self) -> None:
        while self._undo:
            obj, name, value = self._undo.pop()
            setattr(obj, name, value)


class FakeModerators:
    """假的 Helix mod 名單：`lists[頻道 ID]` 是 {user_id: 名稱}，或 channel_mods 的 _Unconfirmable／_Unavailable。"""

    def __init__(self):
        self.lists: dict[int, object] = {}
        self.calls: list[int] = []

    def set(self, channel_id: int | str, *mods: tuple[str, str]) -> None:
        self.lists[int(channel_id)] = dict(mods)

    async def fetch(self, twitch_id: int):
        self.calls.append(twitch_id)
        return self.lists.get(twitch_id, {})


def install_fakes(
    setattr: SetAttr,
    *,
    frontend_url: str,
    allowed_origins: list[str],
    credential_id: int,
    redirect_uri: str = "https://api.example.test/oauth/discord",
):
    """換掉後台對外的依賴（設定、Discord OAuth client、auth server 目錄、Helix mod 名單、各種快取），回傳假的 OAuth client。

    不含資料庫：測試另外把各模組的 `sqldb` 換成交易內的 repo，E2E 直接用暫時資料庫。
    credential_id 要是真的（OAuthToken 有外鍵）。
    """
    setattr(config, "frontend_url", lambda: frontend_url)
    setattr(config, "allowed_origins", lambda: allowed_origins)
    fake_client = SimpleNamespace(
        client_id="cid",
        client_secret="secret",
        redirect_uri=redirect_uri,
        default_scopes=["identify"],
        credential_id=credential_id,
        # 假的 auth server：預設查無此人，各測試可設定 directory.accounts
        directory=FakeDirectory(),
    )
    setattr(auth, "_oauth_client_cache", fake_client)
    setattr(resolver_module, "_directory", fake_client.directory)
    setattr(session, "_followed", {})
    setattr(session, "_inflight", {})
    setattr(session, "_unavailable_until", 0.0)
    setattr(discord_users, "_fetched", {})
    # mod 名單不打真的 Helix：預設每個頻道都沒有 mod，各測試用 `twitch_mods` fixture 設定
    mods = FakeModerators()
    setattr(channel_mods, "_cache", {})
    setattr(channel_mods, "_inflight", {})
    setattr(channel_mods, "_fetch", mods.fetch)
    setattr(channel_mods.twitch_tokens, "bot_user_id_blocking", lambda: BOT_TWITCH_ID)
    fake_client.moderators = mods
    return fake_client


def make_session(repo, user_id=USER_ID, last_used_ago=timedelta(0), session_id="sid") -> str:
    repo.add(
        DashboardSession(
            session_id=session_id,
            discord_user_id=user_id,
            name="Some One",
            avatar=None,
            last_used_at=nowtz() - last_used_ago,
        )
    )
    return session_id


def make_domalyze_session(repo, account_id, user_id: str | None = USER_ID, session_id="dsid") -> str:
    """析域登入的 session；user_id 為 None 時是沒有 Discord 身分的析域 session。"""
    repo.add(
        DashboardSession(
            session_id=session_id,
            discord_user_id=user_id,
            name="willy",
            avatar=None,
            account_id=account_id,
            via_domalyze=True,
            login_method="domalyze",
        )
    )
    return session_id


def make_twitch_session(repo, twitch_id="777", session_id="tsid", login="streamer", name="Streamer") -> str:
    repo.add(
        DashboardSession(
            session_id=session_id,
            discord_user_id=None,
            name=name,
            avatar=f"https://static-cdn.jtvnw.net/{twitch_id}.png",
            login_method="twitch",
            twitch_user_id=twitch_id,
            twitch_login=login,
            twitch_name=name,
            twitch_avatar=f"https://static-cdn.jtvnw.net/{twitch_id}.png",
        )
    )
    return session_id


# ====== 假的 Discord 權限與伺服器 ======

ADMIN = 0x8
MANAGE_CHANNELS = 0x10
MANAGE_GUILD = 0x20
KICK = 0x2
BAN = 0x4
MANAGE_MESSAGES = 0x2000
MANAGE_ROLES = 0x10000000
MODERATE = 0x10000000000


def g(gid: str, name: str, permissions: int = 0, owner: bool = False) -> dict:
    """使用者在伺服器 gid 的成員資料：permissions 是 guild_permissions 的 bits，owner 表示是伺服器擁有者。"""
    return {"id": gid, "name": name, "owner": owner, "permissions": permissions}


def member(user_id: str | int, permissions: int = 0):
    return SimpleNamespace(id=int(user_id), guild_permissions=dpy.Permissions(permissions))


def bot_guild(gid: int, name: str, members=(), owner_id: int = 1, icon: str | None = None):
    by_id = {m.id: m for m in members}
    return SimpleNamespace(
        id=gid,
        name=name,
        owner_id=owner_id,
        icon=SimpleNamespace(url=icon) if icon else None,
        get_member=by_id.get,
    )
