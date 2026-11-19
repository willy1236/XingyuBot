"""EventSub 與聊天室事件的 handler：把 Twitch 事件轉成 bus 事件，並在需要時回聊天室。"""

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime

from twitchAPI.chat import ChatEvent, ChatSub, EventData, JoinedEvent, LeftEvent, NoticeEvent, WhisperEvent
from twitchAPI.helper import first
from twitchAPI.object import eventsub

from starlib import twitch_event_responses
from starlib.database import sqldb
from starlib.messaging import cache_invalidation, get_bus
from starlib.messaging.events.twitch_activity import (
    TwitchPredictionResultEvent,
    TwitchRaidEvent,
    TwitchRedemptionEvent,
    TwitchSubscribeEvent,
    TwitchSubscriptionMessageEvent,
    TwitchWhisperEvent,
)
from starlib.messaging.events.twitch_follow import TwitchFollowEvent
from starlib.messaging.events.twitch_stream import TwitchStreamOfflineEvent, TwitchStreamOnlineEvent
from starlib.twitch_event_responses import EventResponse
from starServer.twitch_bot import speech, state, timers

log = logging.getLogger(__name__)


#: 匿名贈訂的贈送者在回應裡的名稱
ANONYMOUS = "匿名"
#: 追隨回應的間隔：同一個頻道在這段秒數內只感謝第一位追隨者
FOLLOW_RESPONSE_INTERVAL = 10.0

#: 現在的時間（秒，monotonic）；測試可以換掉
_now: Callable[[], float] = time.monotonic
#: 頻道 ID -> 上次發出追隨回應的時間；重啟歸零
_follow_last: dict[int, float] = {}
#: 頻道 ID -> 六種事件回應的有效設定；用到才讀，設定改了就丟掉
_responses: dict[int, dict[str, EventResponse]] = {}
#: 每次收到失效通知加一；讀取途中收到通知時，讀到的舊值不存進快取
_version = 0


def start() -> None:
    """Twitch bot 初始化完成後呼叫一次：註冊事件回應的快取失效 handler。

    Chat 重啟後 READY 會在新的 loop 上再來一次（handler 沿用），這時要把 handler 改綁到新的 loop。
    """
    _register(state.loop)
    state.chat.register_event(ChatEvent.READY, _on_ready)


def stop() -> None:
    """Twitch bot 收尾時呼叫。"""


async def _on_ready(_: EventData) -> None:
    _register(asyncio.get_running_loop())


def _register(loop: asyncio.AbstractEventLoop) -> None:
    cache_invalidation.on_invalidate("twitch_event_response", _on_invalidated, loop)


async def _on_invalidated(key: str | None) -> None:
    """事件回應改了（任何一個實例）：丟掉該頻道的快取，key 為 None 時全部丟掉；下次用到再讀。"""
    global _version
    _version += 1
    if key is None:
        _responses.clear()
    else:
        _responses.pop(int(key), None)


def _load(twitch_id: int) -> dict[str, EventResponse]:
    try:
        return {r.kind: r for r in twitch_event_responses.list_responses(twitch_id)}
    finally:
        sqldb.release_session()


async def _response(twitch_id: int, kind: str) -> EventResponse:
    """頻道這種事件目前有效的設定；讀不到時退回預設文字並視為開啟，不讓 DB 出錯讓回應整個消失。"""
    loaded = _responses.get(twitch_id)
    if loaded is None:
        version = _version
        try:
            loaded = await asyncio.to_thread(_load, twitch_id)
        except Exception:
            log.warning("讀取 %s 的事件回應失敗，改用預設文字", twitch_id, exc_info=True)
            return twitch_event_responses.default_response(kind)
        if version == _version:
            _responses[twitch_id] = loaded
    return loaded[kind]


async def _respond(
    kind: str, twitch_id: int, login: str, channel: str, *, user: str | None = None, **event: str
) -> None:
    """依頻道的事件回應設定在聊天室發言：關閉就不發。任何錯誤只記 log，不影響後面的 bus 事件發布。

    login 是聊天室名稱，channel 是頻道的顯示名稱（`{channel}`）；event 是 `{months}`、`{amount}`、`{viewers}`。
    """
    try:
        response = await _response(twitch_id, kind)
        if not response.enabled:
            return
        ctx = speech.SpeechContext(twitch_id, channel, user=user, event=event)
        await speech.say(login, twitch_id, response.template, ctx, source_kind="event_response", source_key=kind)
    except Exception:
        log.exception("%s 的 %s 事件回應失敗", twitch_id, kind)


def _follow_response_due(twitch_id: int) -> bool:
    """追隨回應的限流：頻道在間隔內已回應過就丟掉這次，不排隊；通過就記下時間。"""
    now = _now()
    last = _follow_last.get(twitch_id)
    if last is not None and now - last < FOLLOW_RESPONSE_INTERVAL:
        return False
    _follow_last[twitch_id] = now
    return True


# eventsub
async def on_follow(event: eventsub.ChannelFollowEvent):
    # await state.chat.send_message(data.event.broadcaster_user_name,text = f'{data.event.user_name} now follows {data.event.broadcaster_user_name}!')
    log.info("%s(%s) now follows %s!", event.event.user_name, event.event.user_login, event.event.broadcaster_user_name)

    broadcaster_id = int(event.event.broadcaster_user_id)
    if _follow_response_due(broadcaster_id):
        await _respond(
            "follow",
            broadcaster_id,
            event.event.broadcaster_user_login,
            event.event.broadcaster_user_name,
            user=event.event.user_name,
        )

    get_bus().publish(
        TwitchFollowEvent(
            occurred_at=event.metadata.message_timestamp,
            broadcaster_id=event.event.broadcaster_user_id,
            broadcaster_name=event.event.broadcaster_user_name,
            follower_name=event.event.user_name,
            follower_login=event.event.user_login,
        )
    )


async def on_stream_online(event: eventsub.StreamOnlineEvent):
    log.info("%s starting stream!", event.event.broadcaster_user_name)

    # 先用事件帶的開台時間記為開台（分類與標題留空），查不到直播時 {uptime} 才不會沿用上一場下播的狀態
    speech.set_live(int(event.event.broadcaster_user_id), speech.StreamInfo(event.event.started_at, "", ""))
    # 事件本身就確認開台，計時訊息不等 Helix：Helix 延遲查不到直播時，計時訊息也要照常開始
    await timers.on_stream_online(int(event.event.broadcaster_user_id))
    # stream.online 會在開台後數秒內送達，此時 Helix streams API 可能還查不到直播，稍等重試
    live = None
    for _ in range(3):
        live = await first(state.twitch.get_streams(user_id=[event.event.broadcaster_user_id]))
        if live:
            break
        await asyncio.sleep(10)
    if live is None:
        log.warning("%s 開台但查不到直播資訊，略過開台通知", event.event.broadcaster_user_name)
        return
    speech.set_live(
        int(event.event.broadcaster_user_id), speech.StreamInfo(live.started_at, live.game_name, live.title)
    )

    # 聊天室訊息只看事件回應的開關；Discord 端的通知頻道與開台通知由 Discord bot 處理事件時決定
    await _respond(
        "stream_online",
        int(event.event.broadcaster_user_id),
        event.event.broadcaster_user_login,
        event.event.broadcaster_user_name,
    )

    try:
        user = await first(state.twitch.get_users(user_ids=[event.event.broadcaster_user_id]))
    except Exception:
        log.warning("%s 的頭像查詢失敗，開台通知改用預設圖", event.event.broadcaster_user_name, exc_info=True)
        user = None
    get_bus().publish(
        TwitchStreamOnlineEvent(
            occurred_at=event.metadata.message_timestamp,
            broadcaster_id=event.event.broadcaster_user_id,
            broadcaster_name=event.event.broadcaster_user_name,
            profile_image_url=user.profile_image_url if user else None,
            stream_id=live.id,
            user_login=live.user_login,
            game_id=live.game_id,
            game_name=live.game_name,
            stream_type=live.type,
            title=live.title,
            viewer_count=live.viewer_count,
            started_at=live.started_at,
            language=live.language,
            thumbnail_url=live.thumbnail_url,
            tag_ids=live.tag_ids or [],
            tags=live.tags or [],
            is_mature=live.is_mature,
        )
    )


async def on_stream_offline(event: eventsub.StreamOfflineEvent):
    log.info("%s ending stream.", event.event.broadcaster_user_name)
    speech.set_offline(int(event.event.broadcaster_user_id))
    await timers.on_stream_offline(int(event.event.broadcaster_user_id))
    get_bus().publish(
        TwitchStreamOfflineEvent(
            occurred_at=event.metadata.message_timestamp,
            broadcaster_id=event.event.broadcaster_user_id,
            broadcaster_name=event.event.broadcaster_user_name,
        )
    )


async def on_channel_points_custom_reward_redemption_add(event: eventsub.ChannelPointsCustomRewardRedemptionAddEvent):
    text = f"{event.event.user_name}({event.event.user_login}) 兌換了 {event.event.reward.title}!"
    if event.event.user_input:
        text += f" ({event.event.user_input})"
    log.info(text)

    # Discord 通知不論通知頻道設定都送出，由 Discord 端決定發不發、發到哪
    get_bus().publish(
        TwitchRedemptionEvent(
            occurred_at=event.metadata.message_timestamp,
            broadcaster_id=event.event.broadcaster_user_id,
            user_name=event.event.user_name,
            user_login=event.event.user_login,
            reward_title=event.event.reward.title,
            user_input=event.event.user_input or None,
        )
    )


async def on_channel_points_custom_reward_redemption_update(
    event: eventsub.ChannelPointsCustomRewardRedemptionUpdateEvent,
):
    log.info(
        "%s's redemption of %s has been updated to %s!",
        event.event.user_name,
        event.event.reward.title,
        event.event.status,
    )


async def on_channel_raid(event: eventsub.ChannelRaidEvent):
    log.info(
        "%s 帶了 %s 位觀眾來 %s 的頻道！",
        event.event.from_broadcaster_user_name,
        event.event.viewers,
        event.event.to_broadcaster_user_name,
    )

    await _respond(
        "raid",
        int(event.event.to_broadcaster_user_id),
        event.event.to_broadcaster_user_login,
        event.event.to_broadcaster_user_name,
        user=event.event.from_broadcaster_user_name,
        viewers=str(event.event.viewers),
    )

    get_bus().publish(
        TwitchRaidEvent(
            occurred_at=event.metadata.message_timestamp,
            to_broadcaster_id=event.event.to_broadcaster_user_id,
            to_broadcaster_name=event.event.to_broadcaster_user_name,
            from_broadcaster_name=event.event.from_broadcaster_user_name,
            viewers=event.event.viewers,
        )
    )


async def on_channel_subscribe(event: eventsub.ChannelSubscribeEvent):
    log.info("%s 在 %s 的層級%s新訂閱", event.event.user_name, event.event.broadcaster_user_name, event.event.tier[0])

    # 贈送訂閱的收禮者不回應也不通知 Discord，由贈訂事件回應一次；其餘不論通知頻道設定都送出，由 Discord 端決定發不發
    if not event.event.is_gift:
        await _respond(
            "subscribe",
            int(event.event.broadcaster_user_id),
            event.event.broadcaster_user_login,
            event.event.broadcaster_user_name,
            user=event.event.user_name,
        )
        get_bus().publish(
            TwitchSubscribeEvent(
                occurred_at=event.metadata.message_timestamp,
                broadcaster_id=event.event.broadcaster_user_id,
                user_name=event.event.user_name,
            )
        )


async def on_channel_subscription_message(event: eventsub.ChannelSubscriptionMessageEvent):
    texts = [
        f"{event.event.user_name} 在 {event.event.broadcaster_user_name} 的{event.event.duration_months}個月 層級{event.event.tier[0]}訂閱",
        f"他已經訂閱 {event.event.cumulative_months} 個月了",
    ]
    if event.event.message:
        texts.append(f"訊息：{event.event.message.text}")

    for text in texts:
        log.info(text)

    await _respond(
        "resubscribe",
        int(event.event.broadcaster_user_id),
        event.event.broadcaster_user_login,
        event.event.broadcaster_user_name,
        user=event.event.user_name,
        months=str(event.event.cumulative_months or event.event.duration_months),
    )

    get_bus().publish(
        TwitchSubscriptionMessageEvent(
            occurred_at=event.metadata.message_timestamp,
            broadcaster_id=event.event.broadcaster_user_id,
            broadcaster_name=event.event.broadcaster_user_name,
            user_name=event.event.user_name,
            tier=event.event.tier,
            duration_months=event.event.duration_months,
            cumulative_months=event.event.cumulative_months,
            message=event.event.message.text if event.event.message else None,
        )
    )


async def on_channel_subscription_gift(event: eventsub.ChannelSubscriptionGiftEvent):
    log.info(
        "%s 在 %s 的層級%s送出的%s份訂閱",
        event.event.user_name,
        event.event.broadcaster_user_name,
        event.event.tier[0],
        event.event.total,
    )
    await _respond(
        "gift",
        int(event.event.broadcaster_user_id),
        event.event.broadcaster_user_login,
        event.event.broadcaster_user_name,
        user=ANONYMOUS if event.event.is_anonymous else event.event.user_name,
        amount=str(event.event.total),
    )


async def on_channel_poll_begin(event: eventsub.ChannelPollBeginEvent):
    log.info("%s 開始了投票：%s", event.event.broadcaster_user_name, event.event.title)


async def on_channel_prediction_begin(event: eventsub.ChannelPredictionEvent):
    log.info(
        "%s 開始了預測：%s\n%s V.S. %s",
        event.event.broadcaster_user_name,
        event.event.title,
        event.event.outcomes[0].title,
        event.event.outcomes[1].title,
    )


async def on_channel_prediction_end(event: eventsub.ChannelPredictionEndEvent):
    if event.event.status == "resolved":
        log.info("%s 結束了預測：%s", event.event.broadcaster_user_name, event.event.title)
        for outcome in event.event.outcomes:
            if outcome.id == event.event.winning_outcome_id:
                log.info("%s (%s) 獲勝！%s個人成功預測", outcome.title, outcome.color, outcome.users)
                get_bus().publish(
                    TwitchPredictionResultEvent(
                        occurred_at=event.metadata.message_timestamp,
                        broadcaster_name=event.event.broadcaster_user_name,
                        title=event.event.title,
                        outcome_title=outcome.title,
                        users=outcome.users,
                    )
                )
    else:
        log.info("%s 取消了預測：%s", event.event.broadcaster_user_name, event.event.title)


async def on_sub(sub: ChatSub):
    log.info("New subscription in %s:", sub.room.name)
    log.info("Type: %s", sub.sub_plan_name)
    log.info("Message: %s", sub.sub_message)
    log.info("System message: %s", sub.system_message)


async def on_bot_joined(event: JoinedEvent):
    await asyncio.sleep(1)
    text = "Joined bot in %s"
    if event.chat.is_mod(event.room_name):
        text += " as mod"
    log.info(text, event.room_name)


async def on_bot_leaved(event: LeftEvent):
    log.info("Leaved bot in %s", event.room_name)


async def on_server_notice(event: NoticeEvent):
    if event.room:
        log.info("Notice from server: %s in %s", event.message, event.room.name)
    else:
        log.info("Notice from server: %s", event.message)


async def on_whisper(event: WhisperEvent):
    log.info("Whisper from %s: %s", event.user.name, event.message)
    # WhisperEvent 沒有 EventSub 的 message_timestamp，以收到時間為事件時間
    get_bus().publish(
        TwitchWhisperEvent(occurred_at=datetime.now(UTC), user_name=event.user.name, message=event.message)
    )


async def on_raid(event: dict):
    try:
        log.info("Raid from %s with %s viewers", event["tags"]["display-name"], event["tags"]["msg-param-viewerCount"])
    except Exception:
        log.warning(event)
