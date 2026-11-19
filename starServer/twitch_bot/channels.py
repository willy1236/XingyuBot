"""頻道的 EventSub 訂閱：啟動時與（之後的）即時同步共用同一套訂閱邏輯，並記住每個訂閱的 id 以便取消。"""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

from twitchAPI.eventsub.webhook import EventSubWebhook
from twitchAPI.object.api import TwitchUser
from twitchAPI.type import EventSubSubscriptionError, EventSubSubscriptionTimeout

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
