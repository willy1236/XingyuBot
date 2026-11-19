"""EventSub 與聊天室事件的 handler：把 Twitch 事件轉成 bus 事件，並在需要時回聊天室。"""

import asyncio
import logging
from datetime import UTC, datetime

from twitchAPI.chat import ChatSub, JoinedEvent, LeftEvent, NoticeEvent, WhisperEvent
from twitchAPI.helper import first
from twitchAPI.object import eventsub

from starlib.messaging import get_bus
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
from starServer.twitch_bot import speech, state, timers

log = logging.getLogger(__name__)


def start() -> None:
    """Twitch bot 初始化完成後呼叫一次；需要註冊快取失效 handler 等啟動工作的功能在這裡做。"""


def stop() -> None:
    """Twitch bot 收尾時呼叫。"""


# eventsub
async def on_follow(event: eventsub.ChannelFollowEvent):
    # await state.chat.send_message(data.event.broadcaster_user_name,text = f'{data.event.user_name} now follows {data.event.broadcaster_user_name}!')
    log.info("%s(%s) now follows %s!", event.event.user_name, event.event.user_login, event.event.broadcaster_user_name)

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
    await timers.on_stream_online(int(event.event.broadcaster_user_id))

    # 聊天室訊息只看有沒有設定通知頻道；Discord 端的通知頻道與開台通知由 Discord bot 處理事件時決定
    channel_config = state.join_channels.get(int(event.event.broadcaster_user_id))
    if channel_config and channel_config.action_channel_id:
        await state.chat.send_message(
            event.event.broadcaster_user_login,
            f"{event.event.broadcaster_user_name} 正在直播 {live.game_name}! {live.title}",
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

    channel_config = state.join_channels.get(int(event.event.to_broadcaster_user_id))
    if channel_config and channel_config.action_channel_id:
        await state.chat.send_message(
            event.event.to_broadcaster_user_login,
            f"{event.event.from_broadcaster_user_name} 帶了 {event.event.viewers} 位觀眾降落在 {event.event.to_broadcaster_user_name} 的頻道！",
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

    # 贈送訂閱不通知 Discord；其餘不論通知頻道設定都送出，由 Discord 端決定發不發
    if not event.event.is_gift:
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

    channel_config = state.join_channels.get(int(event.event.broadcaster_user_id))
    if channel_config and channel_config.action_channel_id:
        chat_text = f"感謝 {event.event.user_name} 的訂閱！"
        if event.event.cumulative_months:
            chat_text += f"累積訂閱{event.event.cumulative_months}個月！"
        await state.chat.send_message(event.event.broadcaster_user_login, chat_text)

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
    channel_config = state.join_channels.get(int(event.event.broadcaster_user_id))
    if channel_config and channel_config.action_channel_id and not event.event.is_anonymous:
        await state.chat.send_message(
            event.event.broadcaster_user_login, f"感謝 {event.event.user_name} 送出的{event.event.total}份訂閱！"
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
