"""頻道的聊天室加入與 EventSub 訂閱：啟動時與 web 的即時同步（RPC）共用同一套邏輯，並記住每個訂閱的 id 以便取消。"""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

import httpx
from twitchAPI.chat import EventData
from twitchAPI.eventsub.webhook import EventSubWebhook
from twitchAPI.helper import first
from twitchAPI.object.api import TwitchUser
from twitchAPI.type import EventSubSubscriptionError, EventSubSubscriptionTimeout

from sentry_bootstrap import capture_exception_safe
from starlib import twitch_tokens
from starlib.database import APIType, TwitchBotJoinChannel, sqldb
from starlib.messaging import cache_invalidation, rpc
from starlib.twitch_tokens import TokenInvalid
from starServer.twitch_bot import events, state

log = logging.getLogger(__name__)

# (EventSub, 實況主 ID, bot 的使用者 ID) -> 訂閱的協程
type Subscriber = Callable[[EventSubWebhook, str, str], Coroutine[Any, Any, str]]

# 任何頻道都訂閱
BASE_EVENTS: dict[str, Subscriber] = {
    "stream online": lambda es, uid, bot: es.listen_stream_online(uid, events.on_stream_online),
    "stream offline": lambda es, uid, bot: es.listen_stream_offline(uid, events.on_stream_offline),
    "channel raid": lambda es, uid, bot: es.listen_channel_raid(events.on_channel_raid, to_broadcaster_user_id=uid),
}

# 需要 bot 是該頻道的 mod 才能訂閱；channel poll begin、channel prediction begin 目前不訂閱，需要時比照加上
MOD_EVENTS: dict[str, Subscriber] = {
    "channel follow": lambda es, uid, bot: es.listen_channel_follow_v2(uid, bot, events.on_follow),
    "channel points custom reward redemption add": lambda es, uid, bot: (
        es.listen_channel_points_custom_reward_redemption_add(
            uid, events.on_channel_points_custom_reward_redemption_add
        )
    ),
    "channel points custom reward redemption update": lambda es, uid, bot: (
        es.listen_channel_points_custom_reward_redemption_update(
            uid, events.on_channel_points_custom_reward_redemption_update
        )
    ),
    "channel subscribe": lambda es, uid, bot: es.listen_channel_subscribe(uid, events.on_channel_subscribe),
    "channel subscription message": lambda es, uid, bot: es.listen_channel_subscription_message(
        uid, events.on_channel_subscription_message
    ),
    "channel subscription gift": lambda es, uid, bot: es.listen_channel_subscription_gift(
        uid, events.on_channel_subscription_gift
    ),
    "channel prediction end": lambda es, uid, bot: es.listen_channel_prediction_end(
        uid, events.on_channel_prediction_end
    ),
}


@dataclass
class Subscriptions:
    """一個頻道目前的 EventSub 訂閱：名稱對應 subscription id，以及最近一次訂閱失敗的名稱。"""

    ids: dict[str, str] = field(default_factory=dict)
    failed: list[str] = field(default_factory=list)


# twitch_id -> 訂閱；只在 Twitch bot 的長駐 loop 上讀寫
subscriptions: dict[int, Subscriptions] = {}


async def _listen(name: str, subscribe: Coroutine[Any, Any, str]) -> str | None:
    """訂閱一個 EventSub 事件，回傳 subscription id；失敗只記 warning 並回傳 None，不影響其他事件。
    每次成功訂閱後間隔 1 秒避免觸發速率限制。"""
    try:
        subscription_id = await subscribe
        log.debug("listening to %s, subscription_id: %s", name, subscription_id)
        await asyncio.sleep(1)
    except EventSubSubscriptionError as e:
        log.warning("Error subscribing to %s: %s", name, e)
        return None
    except EventSubSubscriptionTimeout:
        log.warning("Error subscribing to %s: timeout.", name)
        return None
    return subscription_id


async def subscribe_channel(user: TwitchUser, *, is_mod: bool) -> None:
    """讓頻道的訂閱符合目前狀態：補訂缺少的事件，退掉不該有的（bot 不是 mod 時的 mod 事件）。可重複呼叫。"""
    subs = subscriptions.setdefault(int(user.id), Subscriptions())
    wanted = BASE_EVENTS | (MOD_EVENTS if is_mod else {})
    for name in [n for n in subs.ids if n not in wanted]:
        await unsubscribe(subs, name)
    subs.failed = []
    for name, subscriber in wanted.items():
        if name in subs.ids:
            continue
        subscription_id = await _listen(name, subscriber(state.eventsub, user.id, state.bot_user_id))
        if subscription_id is None:
            subs.failed.append(name)
        else:
            subs.ids[name] = subscription_id


async def unsubscribe(subs: Subscriptions, name: str) -> None:
    subscription_id = subs.ids.pop(name)
    await state.eventsub.unsubscribe_topic(subscription_id)


async def unsubscribe_channel(twitch_id: int) -> None:
    """取消頻道的全部訂閱。"""
    subs = subscriptions.pop(twitch_id, None)
    if subs is None:
        return
    for name in list(subs.ids):
        await unsubscribe(subs, name)


# ── 聊天室與即時同步 ──────────────────────────────────────

# 聊天室加入或離開的上限；比 RPC 的 5 秒短，確保 sync 一定在期限內回應（Chat 的 join_timeout 預設 10 秒）
ROOM_TIMEOUT = 4.0
MODERATORS_URL = "https://api.twitch.tv/helix/moderation/moderators"

# 應該在聊天室裡的頻道：twitch_id -> login。啟動時載入 enabled 的頻道，sync 時增減
rooms: dict[int, str] = {}

# 以下鎖與計數只在 state.loop 上使用；同一頻道的聊天室動作與訂閱調整各自依序執行
_room_locks: dict[int, asyncio.Lock] = {}
_subscription_locks: dict[int, asyncio.Lock] = {}
_pending: dict[int, int] = {}
_client_id: str | None = None


def _lock(locks: dict[int, asyncio.Lock], twitch_id: int) -> asyncio.Lock:
    return locks.setdefault(twitch_id, asyncio.Lock())


_registered = False


async def on_ready(ready_event: EventData) -> None:
    """Chat 連上時：記下它的 loop，並加入目前應該在的聊天室（chat 重啟後也是用這份，不是啟動時的舊清單）。

    `_watch_chat` 重啟 chat 後 READY 會在新的 loop 上再來一次：RPC 與快取失效的 handler 要改綁到新的 loop，
    綁在舊 loop 上的鎖與計數也一併作廢（舊 loop 上還沒跑完的背景任務不會再執行）。
    """
    loop = asyncio.get_running_loop()
    restarted = getattr(state, "loop", loop) is not loop
    if restarted:
        _room_locks.clear()
        _subscription_locks.clear()
        _pending.clear()
    state.loop = loop
    if restarted and _registered:
        register()
    log.info("Bot is ready as %s, joining channels", ready_event.chat.username)
    if rooms:
        await ready_event.chat.join_room(list(rooms.values()))


def _load_row(twitch_id: int) -> TwitchBotJoinChannel | None:
    try:
        return sqldb.get_twitch_join_channel(twitch_id)
    finally:
        sqldb.release_session()


def _load_all() -> dict[int, TwitchBotJoinChannel]:
    try:
        return sqldb.get_bot_join_channel_all()
    finally:
        sqldb.release_session()


async def reload_channel(twitch_id: int) -> TwitchBotJoinChannel | None:
    """重讀單一頻道的設定到 state.join_channels。"""
    row = await asyncio.to_thread(_load_row, twitch_id)
    if row is None:
        state.join_channels.pop(twitch_id, None)
    else:
        state.join_channels[twitch_id] = row
    return row


async def _broadcaster_client_id() -> str:
    global _client_id
    if _client_id is None:

        def read() -> str:
            try:
                return sqldb.get_oauth_client(APIType.Twitch, twitch_tokens.BROADCASTER_CLIENT_SEQ).client_id
            finally:
                sqldb.release_session()

        _client_id = await asyncio.to_thread(read)
    return _client_id


async def bot_is_mod(twitch_id: int) -> bool | None:
    """用實況主的 token 向 Helix 查 bot 是不是頻道 mod，不用 Chat 的 is_mod 快取（拿掉 mod 後它不會更新）。

    拿不到有效的實況主 token、或 token 缺 moderation:read 時視為非 mod；Twitch 暫時無法回應時回 None（不知道）。
    """
    token = await twitch_tokens.broadcaster_token(twitch_id)
    if isinstance(token, TokenInvalid):
        return None if token.reason == "unavailable" else False
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(
                MODERATORS_URL,
                params={"broadcaster_id": str(twitch_id), "user_id": state.bot_user_id},
                headers={"Authorization": f"Bearer {token}", "Client-Id": await _broadcaster_client_id()},
            )
    except httpx.HTTPError as exc:
        log.warning("查詢 %s 的 mod 名單失敗：%r", twitch_id, exc)
        return None
    if response.status_code == 200:
        return bool(response.json()["data"])
    if response.status_code in (401, 403):
        return False
    log.warning("查詢 %s 的 mod 名單失敗：%s %s", twitch_id, response.status_code, response.text)
    return None


async def _get_user(twitch_id: int) -> TwitchUser | None:
    return await first(state.twitch.get_users(user_ids=[str(twitch_id)]))


async def _join(twitch_id: int) -> bool:
    user = await _get_user(twitch_id)
    if user is None:
        log.warning("Twitch 查無頻道 %s，無法加入聊天室", twitch_id)
        return False
    rooms[twitch_id] = user.login
    if state.chat.is_in_room(user.login):
        return True
    return not await state.chat.join_room(user.login)


async def _leave(twitch_id: int, row: TwitchBotJoinChannel | None) -> bool:
    login = rooms.pop(twitch_id, None) or (row.login if row else None)
    if login is None or not state.chat.is_in_room(login):
        return False
    await state.chat.leave_room(login)
    return state.chat.is_in_room(login)


async def sync_channel(twitch_id: int) -> bool:
    """依資料庫的 state 讓 bot 加入（enabled）或離開聊天室，回傳之後是否在聊天室；EventSub 排進背景。

    可重複呼叫：已在聊天室就不再加入，訂閱則依當下的 mod 狀態補訂或退訂。同一頻道依序執行。
    """
    async with _lock(_room_locks, twitch_id):
        row = await reload_channel(twitch_id)
        enabled = row is not None and row.state == "enabled"
        try:
            joined = await asyncio.wait_for(_join(twitch_id) if enabled else _leave(twitch_id, row), ROOM_TIMEOUT)
        except TimeoutError:
            log.warning("頻道 %s 的聊天室%s逾時", twitch_id, "加入" if enabled else "離開")
            joined = state.chat.is_in_room(rooms[twitch_id]) if twitch_id in rooms else False
        except Exception:
            log.exception("頻道 %s 的聊天室同步失敗", twitch_id)
            joined = False
    _pending[twitch_id] = _pending.get(twitch_id, 0) + 1
    asyncio.create_task(_reconcile_in_background(twitch_id))
    return joined


async def _reconcile_in_background(twitch_id: int) -> None:
    try:
        async with _lock(_subscription_locks, twitch_id):
            await reconcile_subscriptions(twitch_id)
    except Exception as exc:
        capture_exception_safe(exc, tags={"service": "twitch", "source": "reconcile_subscriptions"})
        log.exception("頻道 %s 的 EventSub 同步失敗", twitch_id)
    finally:
        _pending[twitch_id] -= 1


async def reconcile_subscriptions(twitch_id: int) -> None:
    """讓頻道的 EventSub 符合資料庫現況：非 enabled 就全部取消，enabled 就依 bot 的 mod 狀態補訂或退訂。"""
    row = state.join_channels.get(twitch_id)
    if row is None or row.state != "enabled":
        await unsubscribe_channel(twitch_id)
        return
    user = await _get_user(twitch_id)
    if user is None:
        return
    is_mod = await bot_is_mod(twitch_id)
    if is_mod is None:
        # 暫時查不到：維持現有的訂閱，不因為一次失敗退訂
        subs = subscriptions.get(twitch_id)
        is_mod = bool(subs and any(name in MOD_EVENTS for name in subs.ids))
    await subscribe_channel(user, is_mod=is_mod)


def channel_status(twitch_id: int) -> dict[str, Any]:
    """已加入的房間與背景訂閱的結果；不打 Twitch API。"""
    login = rooms.get(twitch_id)
    subs = subscriptions.get(twitch_id)
    return {
        "joined": login is not None and state.chat.is_in_room(login),
        "subscriptions": {
            "ok": list(subs.ids) if subs else [],
            "failed": list(subs.failed) if subs else [],
            "pending": _pending.get(twitch_id, 0) > 0,
        },
    }


# ── RPC 與快取失效 ────────────────────────────────────────


async def _rpc_sync(payload: dict[str, Any]) -> dict[str, Any]:
    return {"accepted": True, "joined": await sync_channel(int(payload["twitch_id"]))}


async def _rpc_status(payload: dict[str, Any]) -> dict[str, Any]:
    return channel_status(int(payload["twitch_id"]))


async def _on_channel_invalidated(key: str | None) -> None:
    if key is not None:
        await reload_channel(int(key))
    else:
        state.join_channels = await asyncio.to_thread(_load_all)


def register() -> None:
    """註冊 twitch 服務的 RPC 方法與 twitch_channel 的快取失效；handler 都跑在 Chat 的 loop 上（要先有 state.loop）。

    呼叫過一次之後，每次 Chat 換 loop（重啟）時 `on_ready` 會再呼叫，把 handler 改綁到新的 loop。
    """
    global _registered
    _registered = True
    rpc.handle("channel.sync", _rpc_sync, state.loop)
    rpc.handle("channel.status", _rpc_status, state.loop)
    cache_invalidation.on_invalidate("twitch_channel", _on_channel_invalidated, state.loop)
