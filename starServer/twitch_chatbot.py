import asyncio
import logging
import socket
import threading
from datetime import UTC, datetime

from sqlalchemy.exc import NoResultFound
from twitchAPI.chat import (
    Chat,
    ChatCommand,
    ChatMessage,
    ChatSub,
    EventData,
    JoinedEvent,
    LeftEvent,
    NoticeEvent,
    WhisperEvent,
)
from twitchAPI.chat.middleware import ChannelCommandCooldown, ChannelRestriction
from twitchAPI.eventsub.webhook import EventSubWebhook
from twitchAPI.helper import first
from twitchAPI.oauth import UserAuthenticator
from twitchAPI.object import eventsub
from twitchAPI.twitch import Twitch
from twitchAPI.type import (
    AuthScope,
    ChatEvent,
    EventSubSubscriptionError,
    EventSubSubscriptionTimeout,
    InvalidTokenException,
    MissingScopeException,
)

from sentry_bootstrap import capture_exception_safe, capture_message_safe
from starlib import BaseThread, sclient  # TODO: 全面改用 eventbus
from starlib.database import APIType, sqldb
from starlib.instance import tw_api
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

log = logging.getLogger(__name__)

USER_SCOPE = [
    AuthScope.BITS_READ,
    AuthScope.CHANNEL_BOT,
    AuthScope.CHANNEL_MODERATE,
    AuthScope.CHANNEL_MANAGE_MODERATORS,
    AuthScope.CHANNEL_MANAGE_POLLS,
    AuthScope.CHANNEL_MANAGE_PREDICTIONS,
    AuthScope.CHANNEL_MANAGE_RAIDS,
    AuthScope.CHANNEL_MANAGE_REDEMPTIONS,
    AuthScope.CHANNEL_READ_GOALS,
    AuthScope.CHANNEL_READ_POLLS,
    AuthScope.CHANNEL_READ_PREDICTIONS,
    AuthScope.CHANNEL_READ_REDEMPTIONS,
    AuthScope.CHANNEL_READ_VIPS,
    AuthScope.CHAT_READ,
    AuthScope.CHAT_EDIT,
    AuthScope.MODERATION_READ,
    AuthScope.MODERATOR_MANAGE_BANNED_USERS,
    AuthScope.MODERATOR_MANAGE_BLOCKED_TERMS,
    AuthScope.MODERATOR_MANAGE_CHAT_MESSAGES,
    AuthScope.MODERATOR_MANAGE_CHAT_SETTINGS,
    AuthScope.MODERATOR_READ_CHATTERS,
    AuthScope.MODERATOR_READ_FOLLOWERS,
    AuthScope.USER_BOT,
    AuthScope.USER_EDIT_FOLLOWS,
    AuthScope.USER_MANAGE_BLOCKED_USERS,
    AuthScope.USER_MANAGE_WHISPERS,
    AuthScope.USER_READ_CHAT,
    AuthScope.USER_READ_EMAIL,
    AuthScope.USER_READ_MODERATED_CHANNELS,
    AuthScope.USER_READ_SUBSCRIPTIONS,
    AuthScope.USER_WRITE_CHAT,
    AuthScope.WHISPERS_READ,
    AuthScope.WHISPERS_EDIT,
    ]

# import 時不查 DB，由 run() 開頭的 load_join_channels() 填入；handler 繼續以模組全域讀取
join_channels: dict = {}
TARGET_CHANNEL: dict = {}
TARGET_CHANNEL_IDS: list[str] = []


def load_join_channels() -> None:
    global join_channels, TARGET_CHANNEL, TARGET_CHANNEL_IDS
    join_channels = sclient.sqldb.get_bot_join_channel_all()
    TARGET_CHANNEL = {twitch_id: data.action_channel_id for twitch_id, data in join_channels.items()}
    TARGET_CHANNEL_IDS = [str(i) for i in TARGET_CHANNEL.keys()]

chat:Chat
# eventsub
async def on_follow(event: eventsub.ChannelFollowEvent):
    #await chat.send_message(data.event.broadcaster_user_name,text = f'{data.event.user_name} now follows {data.event.broadcaster_user_name}!')
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

    # stream.online 會在開台後數秒內送達，此時 Helix streams API 可能還查不到直播，稍等重試
    live = None
    for _ in range(3):
        live = tw_api.get_lives(event.event.broadcaster_user_id)[event.event.broadcaster_user_id]
        if live:
            break
        await asyncio.sleep(10)
    if live is None:
        log.warning("%s 開台但查不到直播資訊，略過開台通知", event.event.broadcaster_user_name)
        return

    # 聊天室訊息只看有沒有設定通知頻道；Discord 端的通知頻道與開台通知由 Discord bot 處理事件時決定
    channel_config = join_channels.get(int(event.event.broadcaster_user_id))
    if channel_config and channel_config.action_channel_id:
        await chat.send_message(event.event.broadcaster_user_login, f"{event.event.broadcaster_user_name} 正在直播 {live.game_name}! {live.title}")

    try:
        user = tw_api.get_user_by_id(event.event.broadcaster_user_id)
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
            tag_ids=live.tag_ids,
            tags=live.tags,
            is_mature=live.is_mature,
        )
    )


async def on_stream_offline(event: eventsub.StreamOfflineEvent):
    log.info("%s ending stream.", event.event.broadcaster_user_name)
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


async def on_channel_points_custom_reward_redemption_update(event: eventsub.ChannelPointsCustomRewardRedemptionUpdateEvent):
    log.info("%s's redemption of %s has been updated to %s!", event.event.user_name, event.event.reward.title, event.event.status)


async def on_channel_raid(event:eventsub.ChannelRaidEvent):
    log.info("%s 帶了 %s 位觀眾來 %s 的頻道！", event.event.from_broadcaster_user_name, event.event.viewers, event.event.to_broadcaster_user_name)

    channel_config = join_channels.get(int(event.event.to_broadcaster_user_id))
    if channel_config and channel_config.action_channel_id:
        await chat.send_message(
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

    channel_config = join_channels.get(int(event.event.broadcaster_user_id))
    if channel_config and channel_config.action_channel_id:
        chat_text = f"感謝 {event.event.user_name} 的訂閱！"
        if event.event.cumulative_months:
            chat_text += f"累積訂閱{event.event.cumulative_months}個月！"
        await chat.send_message(event.event.broadcaster_user_login, chat_text)

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
    log.info("%s 在 %s 的層級%s送出的%s份訂閱", event.event.user_name, event.event.broadcaster_user_name, event.event.tier[0], event.event.total)
    channel_config = join_channels.get(int(event.event.broadcaster_user_id))
    if channel_config and channel_config.action_channel_id and not event.event.is_anonymous:
        await chat.send_message(event.event.broadcaster_user_login, f"感謝 {event.event.user_name} 送出的{event.event.total}份訂閱！")


async def on_channel_poll_begin(event: eventsub.ChannelPollBeginEvent):
    log.info("%s 開始了投票：{event.event.title}", event.event.broadcaster_user_name)


async def on_channel_prediction_begin(event: eventsub.ChannelPredictionEvent):
    log.info("%s 開始了預測：{event.event.title}\n{event.event.outcomes[0].title} V.S. {event.event.outcomes[1].title}", event.event.broadcaster_user_name)


async def on_channel_prediction_end(event: eventsub.ChannelPredictionEndEvent):
    if event.event.status == "resolved":
        log.info("%s 結束了預測：{event.event.title}", event.event.broadcaster_user_name)
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
        log.info("%s 取消了預測：{event.event.title}", event.event.broadcaster_user_name)


# bot
async def on_ready(ready_event: EventData):
    log.info("Bot is ready as %s, joining channels", ready_event.chat.username)
    # join our target channel, if you want to join multiple, either call join for each individually
    # or even better pass a list of channels as the argument
    if users_login:
        await ready_event.chat.join_room(users_login)


# this will be called whenever a message in a channel was send by either the bot OR another user
async def on_message(msg: ChatMessage):
    log.info("in %s, %s said: %s", msg.room.name, msg.user.name, msg.text)


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
    get_bus().publish(TwitchWhisperEvent(occurred_at=datetime.now(UTC), user_name=event.user.name, message=event.message))


async def on_raid(event: dict):
    try:
        log.info("Raid from %s with %s viewers", event["tags"]["display-name"], event["tags"]["msg-param-viewerCount"])
    except Exception:
        log.warning(event)


async def add_chat_command(cmd: ChatCommand):
    parameters = cmd.parameter.split(maxsplit=1)
    if len(parameters) < 2:
        await cmd.reply("用法：!add_command <指令> <回覆>")
    else:
        sclient.sqldb.add_twitch_cmd(cmd.room.room_id, parameters[0], parameters[1])
        cmd.chat.register_command(
            parameters[0], respond_to_chat_command, [ChannelRestriction(allowed_channel=cmd.room.name), ChannelCommandCooldown(cooldown_seconds=30)]
        )
        await cmd.reply(f"已新增指令：{parameters[0]}")


async def remove_chat_command(cmd: ChatCommand):
    parameters = cmd.parameter
    if len(parameters) < 1:
        await cmd.reply("用法：!remove_command <指令>")
    else:
        sclient.sqldb.remove_twitch_cmd(cmd.room.room_id, parameters)
        cmd.chat.unregister_command(parameters)
        await cmd.reply(f"已移除指令：{parameters}")


async def list_chat_command(cmd: ChatCommand):
    parameters = cmd.parameter
    if len(parameters) < 1:
        commands = sclient.sqldb.list_chat_command_by_channel(cmd.room.room_id)
        if commands:
            await cmd.reply(f"指令列表：\n{', '.join([i.name for i in commands])}")
        else:
            await cmd.reply("目前沒有設定指令")
    else:
        command = sclient.sqldb.get_chat_command(parameters, cmd.room.room_id)
        if command:
            await cmd.reply(f"{command.name}：{command.response}")
        else:
            await cmd.reply(f"{parameters} 不存在")


async def respond_to_chat_command(cmd: ChatCommand):
    resp = sqldb.get_twitch_cmd_response_cache(cmd.room.room_id, cmd.text[1:])
    if resp:
        log.debug("invoke_chat_command: %s %s", cmd.text[1:], resp.response)
        await cmd.reply(resp.response)


async def modify_channel_information(cmd: ChatCommand):
    pass


async def run():
    load_join_channels()
    app_config = sqldb.get_oauth_client(APIType.Twitch, 2)
    APP_ID = app_config.client_id
    APP_SECRET = app_config.client_secret

    # validate_data = await validate_token(token)
    # if validate_data.get("client_id") != APP_ID:
    #     token, refresh_token = await refresh_access_token(refresh_token, APP_ID, APP_SECRET)
    #     jtoken['token'] = token
    #     jtoken['refresh'] = refresh_token

    # set up twitch api instance and add user authentication with some scopes
    twitch = await Twitch(APP_ID, APP_SECRET)
    try:
        app_token = sqldb.get_bot_oauth_token(APIType.Twitch, 2)
        await twitch.set_user_authentication(app_token.access_token, USER_SCOPE, app_token.refresh_token)
    except (InvalidTokenException, MissingScopeException, NoResultFound):
        log.exception("Twitch token invalid or missing, re-authenticating")
        auth = UserAuthenticator(twitch, USER_SCOPE)
        token, refresh_token = await auth.authenticate()  # type: ignore
        await twitch.set_user_authentication(token, USER_SCOPE, refresh_token)
        me = await first(twitch.get_users())
        app_token.user_id = me.id
        app_token.client_credential_id = app_config.credential_id
        app_token.access_token = token
        app_token.refresh_token = refresh_token
        app_token.scope = twitch.get_user_auth_scope()
        app_token = sqldb.merge(app_token)

    # 使用自帶的函式處理token
    # helper = UserAuthenticationStorageHelper(twitch, USER_SCOPE)
    # await helper.bind()

    me = await first(twitch.get_users())
    users = [user async for user in twitch.get_users(user_ids=TARGET_CHANNEL_IDS)]
    global users_login
    users_login = [user.login for user in users]
    login_id_map = {user.id: user.login for user in users}

    # create chat instance
    global chat
    chat = await Chat(twitch)

    # register the handlers for the events you want
    chat.register_event(ChatEvent.READY, on_ready)
    chat.register_event(ChatEvent.MESSAGE, on_message)
    chat.register_event(ChatEvent.SUB, on_sub)
    chat.register_event(ChatEvent.JOINED, on_bot_joined)
    chat.register_event(ChatEvent.LEFT, on_bot_leaved)
    chat.register_event(ChatEvent.NOTICE, on_server_notice)
    chat.register_event(ChatEvent.WHISPER, on_whisper)
    chat.register_event(ChatEvent.RAID, on_raid)

    # chat.register_command_middleware(ChannelRestriction(allowed_channel=[]))
    chat.register_command("add_cmd", add_chat_command)
    chat.register_command("remove_cmd", remove_chat_command)
    chat.register_command("list_cmd", list_chat_command)
    for twitch_id, cmd in sqldb.get_chat_command_names():
        succ = chat.register_command(
            cmd, respond_to_chat_command, [ChannelRestriction(allowed_channel=login_id_map.get(str(twitch_id))), ChannelCommandCooldown(cooldown_seconds=30)]
        )
        log.debug("register command: %s in %s is %s", cmd, login_id_map.get(str(twitch_id)), succ)
    # TODO: modify_channel_information

    chat.start()
    await asyncio.sleep(5)

    eventsub = EventSubWebhook(app_config.callback_uri, 14001, twitch)
    # unsubscribe from all old events that might still be there
    # this will ensure we have a clean slate
    await eventsub.unsubscribe_all()
    # start the eventsub client
    eventsub.start()
    await asyncio.sleep(3)
    for user in users:
        log.debug("eventsub:%s", user.login)
        try:
            subscription_id = await eventsub.listen_stream_online(user.id, on_stream_online)
            await asyncio.sleep(1)
        except EventSubSubscriptionError as e:
            log.warning("Error subscribing stream online: %s", e)
        except EventSubSubscriptionTimeout:
            log.warning("Error subscribing stream online: timeout.")

        try:
            subscription_id = await eventsub.listen_stream_offline(user.id, on_stream_offline)
            await asyncio.sleep(1)
        except EventSubSubscriptionError as e:
            log.warning("Error subscribing stream offline: %s", e)
        except EventSubSubscriptionTimeout:
            log.warning("Error subscribing stream offline: timeout.")

        try:
            subscription_id = await eventsub.listen_channel_raid(on_channel_raid, to_broadcaster_user_id=user.id)
            await asyncio.sleep(1)
        except EventSubSubscriptionError as e:
            log.warning("Error subscribing channel raid: %s", e)
        except EventSubSubscriptionTimeout:
            log.warning("Error subscribing channel raid: timeout.")

        log.debug("eventsub:%s done.", user.login)

        if not chat.is_mod(user.login):
            continue

        try:
            log.debug("listening to channel follow")
            subscription_id = await eventsub.listen_channel_follow_v2(user.id, me.id, on_follow)
            log.debug("subscription_id: %s", subscription_id)
            await asyncio.sleep(1)
        except EventSubSubscriptionError as e:
            log.warning("Error subscribing to channel follow: %s", e)
        except EventSubSubscriptionTimeout:
            log.warning("Error subscribing to channel follow: timeout.")

        try:
            log.debug("listening to channel points custom reward redemption add")
            subscription_id = await eventsub.listen_channel_points_custom_reward_redemption_add(user.id, on_channel_points_custom_reward_redemption_add)
            log.debug("subscription_id: %s", subscription_id)
            await asyncio.sleep(1)
        except EventSubSubscriptionError as e:
            log.warning("Error subscribing to channel points custom reward redemption add: %s", e)
        except EventSubSubscriptionTimeout:
            log.warning("Error subscribing to channel points custom reward redemption add: timeout.")

        try:
            log.debug("listening to channel points custom reward redemption update")
            subscription_id = await eventsub.listen_channel_points_custom_reward_redemption_update(user.id, on_channel_points_custom_reward_redemption_update)
            log.debug("subscription_id: %s", subscription_id)
            await asyncio.sleep(1)
        except EventSubSubscriptionError as e:
            log.warning("Error subscribing to channel points custom reward redemption update: %s", e)
        except EventSubSubscriptionTimeout:
            log.warning("Error subscribing to channel points custom reward redemption update: timeout.")

        try:
            log.debug("listening to channel subscribe")
            subscription_id = await eventsub.listen_channel_subscribe(user.id, on_channel_subscribe)
            log.debug("subscription_id: %s", subscription_id)
            await asyncio.sleep(1)
        except EventSubSubscriptionError as e:
            log.warning("Error subscribing to channel subscribe: %s", e)
        except EventSubSubscriptionTimeout:
            log.warning("Error subscribing to channel subscribe: timeout.")

        try:
            log.debug("listening to channel subscription message")
            subscription_id = await eventsub.listen_channel_subscription_message(user.id, on_channel_subscription_message)
            log.debug("subscription_id: %s", subscription_id)
            await asyncio.sleep(1)
        except EventSubSubscriptionError as e:
            log.warning("Error subscribing to channel subscription message: %s", e)
        except EventSubSubscriptionTimeout:
            log.warning("Error subscribing to channel subscription message: timeout.")

        try:
            log.debug("listening to channel subscription gift")
            subscription_id = await eventsub.listen_channel_subscription_gift(user.id, on_channel_subscription_gift)
            log.debug("subscription_id: %s", subscription_id)
            await asyncio.sleep(1)
        except EventSubSubscriptionError as e:
            log.warning("Error subscribing to channel subscription gift: %s", e)
        except EventSubSubscriptionTimeout:
            log.warning("Error subscribing to channel subscription gift: timeout.")

        # try:
        #     twitch_log.debug("listening to channel poll begin")
        #     await eventsub.listen_channel_poll_begin(user.id, on_channel_poll_begin)
        # except EventSubSubscriptionError as e:
        #     twitch_log.warning("Error subscribing to channel poll begin: %s", e)

        # try:
        #     twitch_log.debug("listening to channel prediction begin")
        #     await eventsub.listen_channel_prediction_begin(user.id, on_channel_prediction_begin)
        # except EventSubSubscriptionError as e:
        #     twitch_log.warning("Error subscribing to channel prediction begin: %s", e)

        try:
            log.debug("listening to channel prediction end")
            subscription_id = await eventsub.listen_channel_prediction_end(user.id, on_channel_prediction_end)
            log.debug("subscription_id: %s", subscription_id)
        except EventSubSubscriptionError as e:
            log.warning("Error subscribing to channel prediction end: %s", e)
        except EventSubSubscriptionTimeout:
            log.warning("Error subscribing to channel prediction end: timeout.")

        log.debug("eventsub for %s(mod) done.", user.login)

    return chat, twitch, eventsub


TWITCH_CHAT_HOST = "irc-ws.chat.twitch.tv"


def _can_reach(host: str, port: int) -> bool:
    try:
        socket.create_connection((host, port), timeout=5).close()
    except OSError:
        return False
    return True


class TwitchBotThread(BaseThread):
    def __init__(self):
        super().__init__(name="TwitchBotThread")
        self.chat: Chat = None
        self.twitch: Twitch = None
        self.eventsub: EventSubWebhook = None
        # run() 初始化完成、進入 _watch_chat 之前 set；呼叫端等它之後才開始消費事件
        self.ready = threading.Event()
        # 異常結束（放棄重連、未捕捉例外）時為 True；此時 thread 不做 cleanup，由呼叫端限時清理後以非 0 結束
        self.abnormal = False

    def run(self):
        try:
            self.chat, self.twitch, self.eventsub = asyncio.run(run())
            self.ready.set()
            self._watch_chat()
        except Exception as exc:
            capture_exception_safe(exc, tags={"service": "twitch", "source": "thread_run"})
            log.error("TwitchBotThread crashed", exc_info=exc)
            self.abnormal = True
            return
        if not self.abnormal:
            asyncio.run(self.cleanup())

    _CHAT_CHECK_INTERVAL = 60
    # twitchAPI 自己的重連 backoff 合計約 255 秒，斷線超過這個時間才視為它已放棄
    _CHAT_DEAD_CHECKS = 5
    _CHAT_START_TIMEOUT = 300

    def _watch_chat(self):
        """等待停止訊號；期間若聊天室斷線且 twitchAPI 已放棄重連，就重啟 chat。"""
        disconnected_checks = 0
        while not self._stop_event.wait(self._CHAT_CHECK_INTERVAL):
            if self.chat.is_connected():
                disconnected_checks = 0
                continue
            disconnected_checks += 1
            if disconnected_checks < self._CHAT_DEAD_CHECKS:
                continue
            if not _can_reach(TWITCH_CHAT_HOST, 443):
                # 網路還沒恢復，重啟只會讓 chat.start() 卡在連線重試
                continue
            log.warning("Twitch chat 已斷線 %d 秒，重啟 chat", disconnected_checks * self._CHAT_CHECK_INTERVAL)
            try:
                self.chat.stop()
            except Exception as exc:
                capture_exception_safe(exc, tags={"service": "twitch", "source": "watch_chat_stop"})
                log.error("Twitch chat 停止失敗，放棄自動重啟", exc_info=exc)
                self.abnormal = True
                return
            # chat.start() 在連線失敗時會無限等待 startup，放到另一條 thread 並設上限
            starter = threading.Thread(target=self.chat.start, name="TwitchChatRestart", daemon=True)
            starter.start()
            starter.join(self._CHAT_START_TIMEOUT)
            if starter.is_alive():
                message = "Twitch chat 重啟逾時，放棄自動重啟"
                log.warning(message)
                capture_message_safe(message, level="error", tags={"service": "twitch", "source": "watch_chat_restart"})
                self.abnormal = True
                return
            disconnected_checks = 0

    async def cleanup(self):
        """安全地清理所有資源"""
        try:
            if self.eventsub:
                await self.eventsub.stop()
        except Exception as e:
            capture_exception_safe(e, tags={"service": "twitch", "source": "cleanup_eventsub"})
            log.warning("Error stopping eventsub: %s", e)

        try:
            if self.twitch:
                await self.twitch.close()
        except Exception as e:
            capture_exception_safe(e, tags={"service": "twitch", "source": "cleanup_twitch"})
            log.warning("Error closing twitch: %s", e)

        try:
            if self.chat:
                self.chat.stop()
        except Exception as e:
            capture_exception_safe(e, tags={"service": "twitch", "source": "cleanup_chat"})
            log.warning("Error stopping chat: %s", e)


if __name__ == "__main__":
    chat, twitch, eventsub_webhook = asyncio.run(run())
    chat: Chat
    twitch: Twitch
    eventsub_webhook: EventSubWebhook

    try:
        input("press ENTER to stop\n")
    finally:
        chat.stop()
        asyncio.run(twitch.close())
