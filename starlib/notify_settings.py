"""社群推播的設定服務：後台與 Discord 指令共用「解析帳號、新增、修改、移除、確保 YouTube 訂閱」。

全部是同步函式，由呼叫端決定在哪個 executor 執行。DB 步驟與網路步驟刻意分開，讓後台能把
DB 交給 `run_db`、把最長約 70 秒的 YouTube 訂閱等待留在預設 executor。
"""

import json
import logging
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from starlib.database import APIType, Community, NotifyCommunityType, PlatformType, sqldb
from starlib.exceptions import APINetworkError
from starlib.instance import cli_api, google_api, tw_api, yt_push
from starlib.utils import nowtz

log = logging.getLogger(__name__)

type FailureReason = Literal["not_found", "unsupported_format", "platform_unavailable"]


class LookupFailure(Exception):
    """帳號查不到的原因：不存在、格式不支援、平台暫時無法查詢。"""

    def __init__(self, reason: FailureReason):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class AccountInfo:
    platform: PlatformType
    #: 平台帳號 ID
    id: str
    display_name: str | None
    #: 括號裡顯示的帳號；沒有 handle 的 YouTube 頻道是頻道 ID
    username: str

    def to_community(self) -> Community:
        return Community(id=self.id, type=self.platform, display_name=self.display_name, username=self.username)


# ====== 輸入解析 ======
_TWITCH_LOGIN = re.compile(r"[A-Za-z0-9_]{1,25}")
_YT_HANDLE = re.compile(r"[\w.\-]{3,30}")
_YT_CHANNEL_ID = re.compile(r"UC[\w\-]{22}")
_TWITTER_NAME = re.compile(r"\w{1,15}")
_TWITTER_ID = re.compile(r"\d{1,25}")

_HOSTS: dict[PlatformType, tuple[str, ...]] = {
    PlatformType.Twitch: ("twitch.tv",),
    PlatformType.Google: ("youtube.com",),
    PlatformType.Twitter: ("twitter.com", "x.com"),
}
_PREFIXES = ("www.", "m.", "mobile.")
#: Twitter 網址第一段不是帳號的保留路徑
_TWITTER_RESERVED = {"i", "home", "explore", "search", "settings", "notifications", "messages", "intent", "share", "hashtag", "login", "compose"}


@dataclass(frozen=True)
class ParsedInput:
    #: login／handle 用名稱查，id 用平台帳號 ID 查
    kind: Literal["name", "id"]
    value: str


def _url_segments(platform: PlatformType, text: str) -> list[str] | None:
    """輸入是該平台的網址時回傳路徑各段；不是網址回 None；是網址但不是該平台或沒有路徑拋 unsupported_format。"""
    looks_like_url = "/" in text or ":" in text or "?" in text
    lowered = text.lower()
    host_hint = any(lowered.lstrip("/").startswith(h) or f".{h}" in lowered or f"//{h}" in lowered for hosts in _HOSTS.values() for h in hosts)
    if not looks_like_url and not host_hint:
        return None
    parts = urlsplit(text if "//" in text else f"//{text}")
    host = (parts.hostname or "").lower()
    for prefix in _PREFIXES:
        host = host.removeprefix(prefix)
    if host not in _HOSTS[platform]:
        raise LookupFailure("unsupported_format")
    segments = [seg for seg in parts.path.split("/") if seg]
    if not segments:
        raise LookupFailure("unsupported_format")
    return segments


def parse_input(platform: PlatformType, text: str) -> ParsedInput:
    """把使用者輸入的名稱或網址整理成可查詢的名稱或 ID；格式不合法拋 LookupFailure("unsupported_format")。

    網址有沒有 scheme、`www.`、`m.`，後面有沒有路徑或 query 都接受；不分大小寫；YouTube handle 少打 `@` 也接受。
    """
    text = text.strip()
    if not text:
        raise LookupFailure("unsupported_format")
    segments = _url_segments(platform, text)

    if platform == PlatformType.Twitch:
        login = (segments[0] if segments else text).removeprefix("@").lower()
        if not _TWITCH_LOGIN.fullmatch(login):
            raise LookupFailure("unsupported_format")
        return ParsedInput("name", login)

    if platform == PlatformType.Google:
        if segments is None:
            token = text
        elif segments[0].lower() == "channel" and len(segments) > 1:
            token = segments[1]
        elif segments[0].startswith("@"):
            token = segments[0]
        else:
            raise LookupFailure("unsupported_format")
        if _YT_CHANNEL_ID.fullmatch(token):
            return ParsedInput("id", token)
        handle = token.removeprefix("@")
        if not _YT_HANDLE.fullmatch(handle):
            raise LookupFailure("unsupported_format")
        return ParsedInput("name", "@" + handle)

    # Twitter
    name = (segments[0] if segments else text).removeprefix("@")
    if name.lower() in _TWITTER_RESERVED:
        raise LookupFailure("unsupported_format")
    if _TWITTER_ID.fullmatch(name):
        return ParsedInput("id", name)
    if not _TWITTER_NAME.fullmatch(name):
        raise LookupFailure("unsupported_format")
    return ParsedInput("name", name)


# ====== 平台查詢 ======
def _lookup_twitch(parsed: ParsedInput) -> AccountInfo:
    try:
        user = tw_api.get_user_by_id(parsed.value) if parsed.kind == "id" else tw_api.get_user(parsed.value)
    except APINetworkError as e:
        # Twitch 對不合法的 login 回 400
        raise LookupFailure("unsupported_format" if e.status_code == 400 else "platform_unavailable") from e
    if user is None:
        raise LookupFailure("not_found")
    return AccountInfo(PlatformType.Twitch, str(user.id), user.display_name, user.login)


def _lookup_youtube(parsed: ParsedInput) -> AccountInfo:
    try:
        channel = google_api.get_channel(channel_id=parsed.value) if parsed.kind == "id" else google_api.get_channel(handle=parsed.value)
    except APINetworkError as e:
        raise LookupFailure("platform_unavailable") from e
    if channel is None:
        raise LookupFailure("not_found")
    # Community.username 不可為 null，沒有 handle 的頻道存頻道 ID
    return AccountInfo(PlatformType.Google, channel.id, channel.snippet.title, channel.snippet.customUrl or channel.id)


def _lookup_twitter(parsed: ParsedInput) -> AccountInfo:
    try:
        user = cli_api.get_user_details(parsed.value, strict=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError) as e:
        raise LookupFailure("platform_unavailable") from e
    if user is None:
        raise LookupFailure("not_found")
    return AccountInfo(PlatformType.Twitter, str(user.id), user.fullName, user.userName)


_LOOKUPS = {PlatformType.Twitch: _lookup_twitch, PlatformType.Google: _lookup_youtube, PlatformType.Twitter: _lookup_twitter}


def resolve_account(platform: PlatformType, text: str) -> AccountInfo:
    """名稱或網址 → 平台帳號。同步呼叫平台 API，可能長達數十秒，不可在事件迴圈或 run_db 裡執行。

    Raises:
        LookupFailure: 帳號不存在、格式不支援，或平台暫時無法查詢。
    """
    return _LOOKUPS[platform](parse_input(platform, text))


def fetch_account(platform: PlatformType, account_id: str) -> AccountInfo:
    """依平台帳號 ID 重新查詢（快取過期時用）。"""
    return _LOOKUPS[platform](ParsedInput("id", account_id))


# ====== 推播設定（DB） ======
def add_notifies(
    account: AccountInfo, notify_types: list[NotifyCommunityType], guild_id: int, channel_id: int, role_id: int | None, message: str | None
) -> None:
    """新增同一個帳號的一或多種推播。

    Raises:
        NotifyCommunityExistsError: 任一種類已存在，一筆都不寫入。
    """
    sqldb.insert_notify_communities(account.to_community(), notify_types, guild_id, channel_id, role_id, message, cache_time=nowtz())


def set_notify(account: AccountInfo, notify_type: NotifyCommunityType, guild_id: int, channel_id: int, role_id: int | None, message: str | None) -> None:
    """指令用：該筆已存在就修改頻道、身分組、自訂文字，否則新增。"""
    if sqldb.get_notify_community_fresh(notify_type, account.id, guild_id) is None:
        add_notifies(account, [notify_type], guild_id, channel_id, role_id, message)
    else:
        sqldb.add_notify_community(notify_type, account.id, guild_id, channel_id, role_id, message)
        sqldb.merge(account.to_community())


def remove_notify(notify_type: NotifyCommunityType, account_id: str, guild_id: int) -> None:
    """移除推播，含後續清理。"""
    sqldb.remove_notify_community(notify_type, account_id, guild_id)


# ====== YouTube 訂閱 ======
type PushResult = Literal["ok", "pending", "failed"]

#: add_push 與 get_push 之間給 hub 驗證的等待秒數
PUSH_VERIFY_WAIT = 3


@dataclass(frozen=True)
class PushConfig:
    callback_uri: str
    hub_secret: str | None


def youtube_push_config(channel_id: str) -> PushConfig | None:
    """DB 步驟：這個頻道需要（重新）訂閱時回傳訂閱設定；訂閱仍有效回 None。"""
    if not sqldb.get_push_record(channel_id).is_expired:
        return None
    config = sqldb.get_websub_config(APIType.Google, 4)
    return PushConfig(config.callback_uri, config.hub_secret)


def subscribe_youtube_push(channel_id: str, config: PushConfig) -> tuple[PushResult, tuple[datetime, datetime] | None]:
    """網路步驟，不碰 DB，最長約 70 秒。

    回傳 ("ok", (push_at, expire_at)) 訂閱已驗證；("pending", None) 已送出、hub 尚未驗證完，視為成功；
    ("failed", None) 訂閱失敗，推播設定照常存入。
    """
    try:
        if not yt_push.add_push(channel_id, config.callback_uri, config.hub_secret):
            return "failed", None
        time.sleep(PUSH_VERIFY_WAIT)
        data = yt_push.get_push(channel_id, config.callback_uri, config.hub_secret)
    except Exception:
        # APINetworkError，或 hub 回 404 時 get_push 解析 None 的 AttributeError
        log.warning("YouTube 推播訂閱失敗", extra={"channel_id": channel_id}, exc_info=True)
        return "failed", None
    if not data.has_verify:
        return "pending", None
    return "ok", (data.last_successful_verification, data.expiration_time)


def save_push_record(channel_id: str, push_at: datetime, expire_at: datetime) -> None:
    """DB 步驟：存下訂閱驗證結果，保留紀錄原有的其他欄位。"""
    record = sqldb.get_push_record(channel_id)
    record.push_at = push_at
    record.expire_at = expire_at
    sqldb.merge(record)


def ensure_youtube_push(channel_id: str) -> PushResult:
    """指令用：一次做完「判斷、訂閱、存紀錄」。在 executor 的 thread 執行。"""
    try:
        config = youtube_push_config(channel_id)
        if config is None:
            return "ok"
        result, times = subscribe_youtube_push(channel_id, config)
        if times is not None:
            save_push_record(channel_id, *times)
        return result
    finally:
        sqldb.release_session()
