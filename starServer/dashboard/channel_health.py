"""頻道的健康狀態：哪些功能因 Twitch 端的權限問題暫停，載入頻道頁時即時判定，不存 DB。

只有 DB 的 state 是 enabled 的頻道才會判定；未啟用、已停用與已停權（`banned_at` 不為 null）不打任何 Twitch API 或 RPC。
W-12 的營運入口也用 `channel_health` 判斷頻道狀態。

判定來源：
- 實況主 token：`twitch_control.broadcaster_token`（已含續期），再用 validate 端點比對 `ENABLE_SCOPES`
- Helix Get Moderators、Get Banned Users、Get User Block List：bot 是不是 mod、有沒有被 ban 或封鎖
  （不用 Chat 的 is_mod，它是快取，拿掉 mod 後不會更新）
- `twitch_control.channel_status`：bot 在不在線、在不在聊天室、EventSub 訂閱的結果

任何一項查不到（Twitch 暫時無法回應、逾時）就略過那一項，不當成有問題，也不擋其他項目。
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Literal, cast

import httpx

from starlib import sqldb, twitch_speech_check
from starlib.database import TwitchBotJoinChannel
from starlib.messaging.rpc import RpcHandlerError
from starlib.twitch_tokens import MODERATORS_URL, TokenInvalid, bot_user_id_blocking

from . import twitch_control
from .db import run_db

log = logging.getLogger(__name__)

type HealthState = Literal["inactive", "enabled", "partial", "disabled", "banned"]
type Issue = Literal["token_invalid", "not_mod", "bot_banned", "not_joined", "subscription_failed", "bot_offline"]

#: issues 依這個順序輸出
ISSUE_ORDER: tuple[Issue, ...] = (
    "token_invalid",
    "not_mod",
    "bot_banned",
    "not_joined",
    "subscription_failed",
    "bot_offline",
)

REQUEST_TIMEOUT = 5.0
#: 整個 Twitch 判定（token 續期、validate、三項查詢）的總時限，逾時視同查不到；比單次請求的 5 秒長，容得下一次續期加後續查詢
ACCESS_TIMEOUT = 8.0
VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"
BANNED_URL = "https://api.twitch.tv/helix/moderation/banned"
BLOCKS_URL = "https://api.twitch.tv/helix/users/blocks"
#: Get User Block List 沒有 user 篩選，要翻頁找 bot；每頁 100 筆，超過這個頁數就當查不到
BLOCK_LIST_MAX_PAGES = 5

#: 需要 bot 是頻道 mod 才能訂閱的 EventSub 事件；與 twitch_bot.channels.MOD_EVENTS 的名稱一致（有測試比對）
EVENTS_NEED_MOD = frozenset(
    {
        "channel follow",
        "channel points custom reward redemption add",
        "channel points custom reward redemption update",
        "channel subscribe",
        "channel subscription message",
        "channel subscription gift",
        "channel prediction end",
    }
)


@dataclass(frozen=True, slots=True)
class Feature:
    """code：功能代碼（前端用它對應名稱）；chat：靠 bot 在聊天室發言；events：依賴的 EventSub 事件。"""

    code: str
    chat: bool
    events: tuple[str, ...] = ()

    @property
    def needs_mod(self) -> bool:
        return not EVENTS_NEED_MOD.isdisjoint(self.events)


#: 所有功能都要實況主 token（發言前的 AutoMod 檢查、EventSub 訂閱），所以 token 失效時全部暫停。
#: 功能代碼上線後前端與 W-12 都會用，不要改名。
FEATURES: tuple[Feature, ...] = (
    Feature("speech", chat=True),
    Feature("stream_online_response", chat=True, events=("stream online",)),
    Feature("raid_response", chat=True, events=("channel raid",)),
    Feature("follow_response", chat=True, events=("channel follow",)),
    Feature("follow_forward", chat=False, events=("channel follow",)),
    Feature("subscribe_response", chat=True, events=("channel subscribe",)),
    Feature("subscribe_forward", chat=False, events=("channel subscribe",)),
    Feature("resubscribe_response", chat=True, events=("channel subscription message",)),
    Feature("resubscribe_forward", chat=False, events=("channel subscription message",)),
    Feature("gift_response", chat=True, events=("channel subscription gift",)),
    Feature("gift_forward", chat=False, events=("channel subscription gift",)),
    Feature(
        "redemption_forward",
        chat=False,
        events=("channel points custom reward redemption add", "channel points custom reward redemption update"),
    ),
    Feature("prediction_forward", chat=False, events=("channel prediction end",)),
)


@dataclass(frozen=True, slots=True)
class ChannelHealth:
    state: HealthState
    issues: tuple[Issue, ...] = ()
    paused_features: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {"state": self.state, "issues": list(self.issues), "paused_features": list(self.paused_features)}


@dataclass(frozen=True, slots=True)
class _Access:
    """Twitch 端的權限判定；None 表示查不到。"""

    token_invalid: bool = False
    is_mod: bool | None = None
    bot_banned: bool = False


def _json(response: httpx.Response) -> dict | None:
    """回應內容是 JSON 物件才回傳，解析失敗或不是物件回 None。"""
    try:
        body = response.json()
    except ValueError:
        return None
    return body if isinstance(body, dict) else None


async def _get(client: httpx.AsyncClient, url: str, headers: dict[str, str], **params: str | int) -> dict | None:
    """Helix 查詢；失敗、回應不是 JSON 物件、或沒有 `data` 清單都回 None（各項判定各自略過）。"""
    try:
        response = await client.get(url, params=params, headers=headers)
    except httpx.HTTPError as exc:
        log.warning("查詢 %s 失敗：%r", url, exc)
        return None
    if response.status_code != 200:
        log.warning("查詢 %s 失敗：%s %s", url, response.status_code, response.text)
        return None
    body = _json(response)
    if body is None or not isinstance(body.get("data"), list):
        log.warning("查詢 %s 的回應格式不符：%s", url, response.text)
        return None
    return body


async def _token_rejected(client: httpx.AsyncClient, token: str) -> bool:
    """validate 端點回 401 或缺少必要的 scope 就是授權失效；查不到不算。"""
    from .channel_activation import ENABLE_SCOPES  # 延遲 import：channel_activation 會 import channels，頂層會循環

    try:
        response = await client.get(VALIDATE_URL, headers={"Authorization": f"OAuth {token}"})
    except httpx.HTTPError as exc:
        log.warning("validate 失敗：%r", exc)
        return False
    if response.status_code == 401:
        return True
    if response.status_code != 200:
        log.warning("validate 失敗：%s %s", response.status_code, response.text)
        return False
    body = _json(response)
    scopes = None if body is None else body.get("scopes")
    if not isinstance(scopes, list):
        log.warning("validate 的回應格式不符：%s", response.text)
        return False
    return not set(ENABLE_SCOPES) <= set(scopes)


async def _is_mod(client: httpx.AsyncClient, headers: dict[str, str], twitch_id: int, bot_id: str) -> bool | None:
    data = await _get(client, MODERATORS_URL, headers, broadcaster_id=str(twitch_id), user_id=bot_id)
    return None if data is None else bool(data["data"])


async def _is_banned(client: httpx.AsyncClient, headers: dict[str, str], twitch_id: int, bot_id: str) -> bool | None:
    data = await _get(client, BANNED_URL, headers, broadcaster_id=str(twitch_id), user_id=bot_id)
    return None if data is None else bool(data["data"])


async def _is_blocked(client: httpx.AsyncClient, headers: dict[str, str], twitch_id: int, bot_id: str) -> bool | None:
    cursor: str | None = None
    for _ in range(BLOCK_LIST_MAX_PAGES):
        params: dict[str, str | int] = {"broadcaster_id": str(twitch_id), "first": 100}
        if cursor:
            params["after"] = cursor
        data = await _get(client, BLOCKS_URL, headers, **params)
        if data is None:
            return None
        if any(isinstance(entry, dict) and entry.get("user_id") == bot_id for entry in data["data"]):
            return True
        pagination = data.get("pagination")
        cursor = pagination.get("cursor") if isinstance(pagination, dict) else None
        if not cursor:
            return False
    return None


async def _check_access(twitch_id: int) -> _Access:
    """整個 Twitch 判定受 `ACCESS_TIMEOUT` 限制：逾時、出錯都回「全部查不到」，不擋頁面載入。"""
    try:
        return await asyncio.wait_for(_query_access(twitch_id), ACCESS_TIMEOUT)
    except TimeoutError:
        log.warning("判定頻道 %s 的 Twitch 權限逾時", twitch_id)
    except Exception:
        log.exception("判定頻道 %s 的 Twitch 權限失敗", twitch_id)
    return _Access()


async def _query_access(twitch_id: int) -> _Access:
    token = await twitch_control.broadcaster_token(twitch_id)
    if isinstance(token, TokenInvalid):
        # unavailable 是 Twitch 暫時無法回應，授權不一定失效：不判定
        return _Access(token_invalid=token.reason != "unavailable")
    client_id = await run_db(twitch_speech_check.broadcaster_client_id_blocking)
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        if await _token_rejected(client, token):
            return _Access(token_invalid=True)
        bot_id = await run_db(bot_user_id_blocking)
        headers = {"Authorization": f"Bearer {token}", "Client-Id": client_id}
        is_mod, banned, blocked = await asyncio.gather(
            _is_mod(client, headers, twitch_id, bot_id),
            _is_banned(client, headers, twitch_id, bot_id),
            _is_blocked(client, headers, twitch_id, bot_id),
        )
    return _Access(is_mod=is_mod, bot_banned=bool(banned or blocked))


async def _bot_status(twitch_id: int) -> twitch_control.ChannelStatus | twitch_control.BotOffline:
    try:
        return await twitch_control.channel_status(twitch_id)
    except RpcHandlerError:
        log.exception("查詢頻道 %s 的 bot 狀態失敗", twitch_id)
        return twitch_control.BotOffline()


def _paused(feature: Feature, issues: set[Issue], failed: set[str]) -> bool:
    if "token_invalid" in issues or "bot_banned" in issues:
        return True
    if "not_mod" in issues and feature.needs_mod:
        return True
    if "not_joined" in issues and feature.chat:
        return True
    return not failed.isdisjoint(feature.events)


def _judge(access: _Access, status: twitch_control.ChannelStatus | twitch_control.BotOffline) -> ChannelHealth:
    issues: set[Issue] = set()
    failed: set[str] = set()
    if access.token_invalid:
        issues.add("token_invalid")
    if access.is_mod is False:
        issues.add("not_mod")
    if access.bot_banned:
        issues.add("bot_banned")
    if isinstance(status, twitch_control.BotOffline):
        issues.add("bot_offline")
    else:
        # ban 或 token 失效已經解釋了進不去聊天室與訂閱失敗，不重複列
        if not status.joined and not access.bot_banned:
            issues.add("not_joined")
        if not (status.subscriptions.pending or access.token_invalid or access.bot_banned):
            failed = set(status.subscriptions.failed)
            if access.is_mod is False:
                failed -= EVENTS_NEED_MOD
            if failed:
                issues.add("subscription_failed")
    paused = tuple(f.code for f in FEATURES if _paused(f, issues, failed))
    ordered: tuple[Issue, ...] = tuple(issue for issue in ISSUE_ORDER if issue in issues)
    return ChannelHealth("partial" if paused else "enabled", ordered, paused)


async def channel_health(twitch_id: int) -> ChannelHealth:
    """頻道目前的狀態、問題與暫停的功能。不 raise Twitch 或 bot 的錯誤，查不到的項目略過。

    state 是 inactive、enabled、partial（有功能暫停）、disabled、banned（停權優先於 DB 的 state）；
    只有 bot 離線時仍是 enabled，不暫停任何功能。
    """
    row = await run_db(lambda: sqldb.get(TwitchBotJoinChannel, (twitch_id,)))
    if row is not None and row.banned_at is not None:
        return ChannelHealth("banned")
    state = "inactive" if row is None else row.state
    if state != "enabled":
        return ChannelHealth(cast(HealthState, state))
    access, status = await asyncio.gather(_check_access(twitch_id), _bot_status(twitch_id))
    return _judge(access, status)
