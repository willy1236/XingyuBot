"""後台端點控制 Twitch bot 的入口：叫 bot 加入或離開頻道、查頻道狀態、通知 bot 重讀設定。

Twitch bot 是另一個 process，這裡只包 RPC 與快取失效，介面見 docs/messaging-contract.md〈twitch 服務〉。
"""

import asyncio
from dataclasses import dataclass
from typing import Literal

from starlib import twitch_speech_check, twitch_tokens
from starlib.messaging import cache_invalidation, rpc
from starlib.twitch_speech_check import TemplateCheck
from starlib.twitch_tokens import TokenInvalid
from starServer.dashboard.db import run_db

SERVICE = "twitch"

type CacheName = Literal["twitch_channel", "twitch_cmd", "twitch_timer", "twitch_event_response", "twitch_regular"]


@dataclass(frozen=True, slots=True)
class SyncResult:
    """joined 表示聊天室已處理完成後 bot 是否在該頻道的聊天室；EventSub 訂閱在背景進行，結果見 `channel_status`。"""

    joined: bool


@dataclass(frozen=True, slots=True)
class SubscriptionStatus:
    ok: list[str]
    failed: list[str]
    pending: bool


@dataclass(frozen=True, slots=True)
class ChannelStatus:
    joined: bool
    subscriptions: SubscriptionStatus


@dataclass(frozen=True, slots=True)
class BotStatus:
    started_at: str | None
    rooms: int


class BotOffline:
    """Twitch bot 沒在跑、Redis 連不上或沒在期限內回應。"""

    __slots__ = ()

    def __repr__(self) -> str:
        return "BotOffline"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, BotOffline)

    def __hash__(self) -> int:
        return hash(BotOffline)


async def _call(method: str, twitch_id: int | None = None) -> dict | BotOffline:
    payload = {} if twitch_id is None else {"twitch_id": twitch_id}
    try:
        return await asyncio.wrap_future(rpc.request(SERVICE, method, payload))
    except rpc.RpcUnavailable:
        return BotOffline()


async def sync_channel(twitch_id: int) -> SyncResult | BotOffline:
    """讓 bot 依資料庫的 state 加入或離開頻道；已加入的頻道再呼叫會補訂或退訂 EventSub。bot 離線時回 BotOffline，不 raise。

    bot 內部出錯時拋 `rpc.RpcHandlerError`，不當成離線。
    """
    result = await _call("channel.sync", twitch_id)
    if isinstance(result, BotOffline):
        return result
    return SyncResult(joined=bool(result["joined"]))


async def channel_status(twitch_id: int) -> ChannelStatus | BotOffline:
    """bot 目前對頻道的狀態：是否在聊天室、各 EventSub 訂閱的結果。bot 離線時回 BotOffline，不 raise。"""
    result = await _call("channel.status", twitch_id)
    if isinstance(result, BotOffline):
        return result
    subscriptions = result["subscriptions"]
    return ChannelStatus(
        joined=bool(result["joined"]),
        subscriptions=SubscriptionStatus(
            ok=list(subscriptions["ok"]), failed=list(subscriptions["failed"]), pending=bool(subscriptions["pending"])
        ),
    )


async def bot_status() -> BotStatus | BotOffline:
    """Twitch bot process 的啟動時間（ISO）與已加入的聊天室數。bot 離線時回 BotOffline；bot 內部出錯時拋 `rpc.RpcHandlerError`。"""
    result = await _call("bot.status")
    if isinstance(result, BotOffline):
        return result
    return BotStatus(started_at=result["started_at"], rooms=int(result["rooms"]))


async def broadcaster_token(twitch_id: int) -> str | TokenInvalid:
    """實況主的 Twitch token，快過期時先續期。DB 工作走後台專屬的 executor（`run_db`），不佔 asyncio 預設 executor。不 raise。"""
    return await run_db(lambda: twitch_tokens.broadcaster_token_blocking(twitch_id))


async def broadcaster_credentials(twitch_id: int) -> tuple[str, str] | TokenInvalid:
    """實況主的 access token 與它所屬的 Twitch OAuth 應用程式 client ID。"""
    token = await broadcaster_token(twitch_id)
    if isinstance(token, TokenInvalid):
        return token
    return token, await run_db(twitch_speech_check.broadcaster_client_id_blocking)


async def check_template(twitch_id: int, template: str) -> TemplateCheck:
    """檢查實況主寫的模板會不會被頻道 AutoMod 擋下（ok、blocked、unavailable），不 raise。

    W-05～W-07 的儲存端點先呼叫它：blocked 回 422 automod_blocked，unavailable 回 503 automod_unavailable。
    token 與 client id 的 DB 查詢走後台專屬的 executor。
    """
    return await twitch_speech_check.check_template(twitch_id, template, get_credentials=broadcaster_credentials)


def invalidate(cache: CacheName, twitch_id: int) -> None:
    """通知 bot 重讀某頻道的設定或常客名單。bot 沒在跑時沒有影響，下次啟動會重讀。"""
    cache_invalidation.invalidate(cache, str(twitch_id))
