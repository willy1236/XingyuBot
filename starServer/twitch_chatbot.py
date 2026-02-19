import asyncio
from pathlib import PurePath
from typing import TYPE_CHECKING
from uuid import UUID

from twitchAPI.chat import Chat, ChatCommand, ChatMessage, ChatSub, EventData, JoinedEvent, LeftEvent, NoticeEvent, WhisperEvent
from twitchAPI.chat.middleware import ChannelCommandCooldown, ChannelRestriction
from twitchAPI.eventsub.webhook import EventSubWebhook
from twitchAPI.eventsub.websocket import EventSubWebsocket
from twitchAPI.helper import first
from twitchAPI.oauth import UserAuthenticationStorageHelper, UserAuthenticator, refresh_access_token, validate_token
from twitchAPI.object import eventsub
from twitchAPI.twitch import Twitch
from twitchAPI.type import AuthScope, ChatEvent, EventSubSubscriptionError, EventSubSubscriptionTimeout, InvalidTokenException, MissingScopeException

from starlib import BaseThread, BotEmbed, Jsondb, sclient, twitch_log  # TODO: 全面改用 eventbus
from starlib.core.model import TwitchStreamEvent
from starlib.database import APIType, NotifyCommunityType, TwitchChatCommand, sqldb
from starlib.instance import tw_api

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

join_channels = sclient.sqldb.get_bot_join_channel_all()
TARGET_CHANNEL = {twitch_id: data.action_channel_id for twitch_id, data in join_channels.items()}
TARGET_CHANNEL_IDS = [str(i) for i in TARGET_CHANNEL.keys()]

chat:"Chat"
# eventsub
async def on_follow(event: eventsub.ChannelFollowEvent):
    #await chat.send_message(data.event.broadcaster_user_name,text = f'{data.event.user_name} now follows {data.event.broadcaster_user_name}!')
    twitch_log.info(f"%s(%s) now follows %s!", event.event.user_name, event.event.user_login, event.event.broadcaster_user_name)

    channel_config = join_channels.get(int(event.event.broadcaster_user_id))
    if channel_config and channel_config.action_channel_id:
        sclient.publish(TwitchStreamEvent(content=f"{event.event.user_name}({event.event.user_login}) 正在追隨 {event.event.broadcaster_user_name}!", to_discord_channel=channel_config.action_channel_id))


async def on_stream_online(event: eventsub.StreamOnlineEvent):
    twitch_log.info(f"%s starting stream!", event.event.broadcaster_user_name)

    live = tw_api.get_lives(event.event.broadcaster_user_id)[event.event.broadcaster_user_id]
    channel_config = join_channels.get(int(event.event.broadcaster_user_id))
    if channel_config and channel_config.action_channel_id:
        await chat.send_message(event.event.broadcaster_user_login, f"{event.event.broadcaster_user_name} 正在直播 {live.game_name}! {live.title}")

        sclient.publish(TwitchStreamEvent(content=f"{event.event.broadcaster_user_name} 正在直播 {live.game_name}!", to_discord_channel=channel_config.action_channel_id))
        is_live = bool(sclient.sqldb.get_community_cache(NotifyCommunityType.TwitchLive, event.event.broadcaster_user_id))
        twitch_log.debug(f"%s is live: %s", event.event.broadcaster_user_name, is_live)
        if not is_live:
            profile_image_url = tw_api.get_user_by_id(event.event.broadcaster_user_id).profile_image_url
            embed = live.embed(profile_image_url)
            sclient.bot.submit(sclient.bot.send_notify_communities(embed, NotifyCommunityType.TwitchLive, event.event.broadcaster_user_id))
            sclient.sqldb.set_community_cache(NotifyCommunityType.TwitchLive, event.event.broadcaster_user_id, live.started_at)


async def on_stream_offline(event: eventsub.StreamOfflineEvent):
    twitch_log.info(f"%s ending stream.", event.event.broadcaster_user_name)
    sclient.publish(TwitchStreamEvent(content=f"{event.event.broadcaster_user_name} ending stream."))

    is_live = bool(sclient.sqldb.get_community_cache(NotifyCommunityType.TwitchLive, event.event.broadcaster_user_id))
    if is_live:
        sclient.sqldb.set_community_cache(NotifyCommunityType.TwitchLive, event.event.broadcaster_user_id, None)


async def on_channel_points_custom_reward_redemption_add(event: eventsub.ChannelPointsCustomRewardRedemptionAddEvent):
    text = f"{event.event.user_name}({event.event.user_login}) 兌換了 {event.event.reward.title}!"
    if event.event.user_input:
        text += f" ({event.event.user_input})"
    twitch_log.info(text)

    channel_config = join_channels.get(int(event.event.broadcaster_user_id))
    if channel_config and channel_config.action_channel_id:
        sclient.publish(TwitchStreamEvent(content=text, to_discord_channel=channel_config.action_channel_id))


async def on_channel_points_custom_reward_redemption_update(event: eventsub.ChannelPointsCustomRewardRedemptionUpdateEvent):
    twitch_log.info(f"%s's redemption of %s has been updated to %s!", event.event.user_name, event.event.reward.title, event.event.status)


async def on_channel_raid(event:eventsub.ChannelRaidEvent):
    twitch_log.info(f"%s 帶了 %s 位觀眾來 %s 的頻道！", event.event.from_broadcaster_user_name, event.event.viewers, event.event.to_broadcaster_user_name)

    channel_config = join_channels.get(int(event.event.to_broadcaster_user_id))
    if channel_config and channel_config.action_channel_id:
        await chat.send_message(
            event.event.to_broadcaster_user_login,
            f"{event.event.from_broadcaster_user_name} 帶了 {event.event.viewers} 位觀眾降落在 {event.event.to_broadcaster_user_name} 的頻道！",
        )

        sclient.publish(
            TwitchStreamEvent(content=f"{event.event.from_broadcaster_user_name} 帶了 {event.event.viewers} 位觀眾降落在 {event.event.to_broadcaster_user_name} 的頻道!", to_discord_channel=channel_config.action_channel_id)
        )


async def on_channel_subscribe(event: eventsub.ChannelSubscribeEvent):
    twitch_log.info(f"%s 在 %s 的層級%s新訂閱", event.event.user_name, event.event.broadcaster_user_name, event.event.tier[0])

    channel_config = join_channels.get(int(event.event.broadcaster_user_id))
    if channel_config and channel_config.action_channel_id and not event.event.is_gift:
        # await chat.send_message(event.event.broadcaster_user_login, f"感謝 {event.event.user_name} 的訂閱！")
        sclient.publish(TwitchStreamEvent(content=f"感謝 {event.event.user_name} 的訂閱！", to_discord_channel=channel_config.action_channel_id))


async def on_channel_subscription_message(event: eventsub.ChannelSubscriptionMessageEvent):
    texts = [
        f"{event.event.user_name} 在 {event.event.broadcaster_user_name} 的{event.event.duration_months}個月 層級{event.event.tier[0]}訂閱",
        f"他已經訂閱 {event.event.cumulative_months} 個月了",
    ]
    if event.event.message:
        texts.append(f"訊息：{event.event.message.text}")

    for text in texts:
        twitch_log.info(text)

    channel_config = join_channels.get(int(event.event.broadcaster_user_id))
    if channel_config and channel_config.action_channel_id:
        chat_text = f"感謝 {event.event.user_name} 的訂閱！"
        if event.event.cumulative_months:
            chat_text += f"累積訂閱{event.event.cumulative_months}個月！"
        await chat.send_message(event.event.broadcaster_user_login, chat_text)

        sclient.publish(TwitchStreamEvent(content=f"感謝 {event.event.user_name} 的訂閱！\n累積訂閱{event.event.cumulative_months}個月！", to_discord_channel=channel_config.action_channel_id))
        sclient.publish(TwitchStreamEvent(content="\n".join(texts), to_discord_channel=channel_config.action_channel_id))


async def on_channel_subscription_gift(event: eventsub.ChannelSubscriptionGiftEvent):
    twitch_log.info(f"{event.event.user_name} 在 {event.event.broadcaster_user_name} 送出的{event.event.total}份層級{event.event.tier[0]}訂閱")
    channel_config = join_channels.get(int(event.event.broadcaster_user_id))
    if channel_config and channel_config.action_channel_id and not event.event.is_anonymous:
        await chat.send_message(event.event.broadcaster_user_login, f"感謝 {event.event.user_name} 送出的{event.event.total}份訂閱！")


async def on_channel_poll_begin(event: eventsub.ChannelPollBeginEvent):
    twitch_log.info(f"{event.event.broadcaster_user_name} 開始了投票：{event.event.title}")
    sclient.publish(TwitchStreamEvent(content=f"{event.event.broadcaster_user_name} 開始了投票：{event.event.title}\n{event.event.choices}"))


async def on_channel_prediction_begin(event: eventsub.ChannelPredictionEvent):
    twitch_log.info(
        f"{event.event.broadcaster_user_name} 開始了預測：{event.event.title}\n{event.event.outcomes[0].title} V.S. {event.event.outcomes[1].title}"
    )
    sclient.publish(TwitchStreamEvent(content=f"{event.event.broadcaster_user_name} 開始了預測：{event.event.title}\n{event.event.outcomes[0].title} V.S. {event.event.outcomes[1].title}"))


async def on_channel_prediction_end(event: eventsub.ChannelPredictionEndEvent):
    if event.event.status == "resolved":
        twitch_log.info(f"{event.event.broadcaster_user_name} 結束了預測：{event.event.title}")
        for outcome in event.event.outcomes:
            if outcome.id == event.event.winning_outcome_id:
                twitch_log.info(f"{outcome.title} ({outcome.color}) 獲勝！{outcome.users}個人成功預測")
                sclient.publish(TwitchStreamEvent(embed=BotEmbed.general(event.event.broadcaster_user_name, description=f"{event.event.title}\n{outcome.title} 獲勝！{outcome.users}個人成功預測")))
    else:
        twitch_log.info(f"{event.event.broadcaster_user_name} 取消了預測：{event.event.title}")


# bot
async def on_ready(ready_event: EventData):
    twitch_log.info("Bot is ready as %s, joining channels", ready_event.chat.username)
    # join our target channel, if you want to join multiple, either call join for each individually
    # or even better pass a list of channels as the argument
    if users_login:
        await ready_event.chat.join_room(users_login)


# this will be called whenever a message in a channel was send by either the bot OR another user
async def on_message(msg: ChatMessage):
    twitch_log.info("in %s, %s said: %s", msg.room.name, msg.user.name, msg.text)


async def on_sub(sub: ChatSub):
    twitch_log.info("New subscription in %s:", sub.room.name)
    twitch_log.info("Type: %s", sub.sub_plan_name)
    twitch_log.info("Message: %s", sub.sub_message)
    twitch_log.info("System message: %s", sub.system_message)


async def on_bot_joined(event: JoinedEvent):
    await asyncio.sleep(1)
    text = "Joined bot in %s"
    if event.chat.is_mod(event.room_name):
        text += " as mod"
    twitch_log.info(text, event.room_name)


async def on_bot_leaved(event: LeftEvent):
    twitch_log.info("Leaved bot in %s", event.room_name)


async def on_server_notice(event: NoticeEvent):
    if event.room:
        twitch_log.info("Notice from server: %s in %s", event.message, event.room.name)
    else:
        twitch_log.info("Notice from server: %s", event.message)


async def on_whisper(event: WhisperEvent):
    twitch_log.info("Whisper from %s: %s", event.user.name, event.message)
    sclient.publish(TwitchStreamEvent(embed=BotEmbed.general(event.user.name, Jsondb.get_picture("twitch_001"), description=event.message)))


async def on_raid(event: dict):
    try:
        twitch_log.info("Raid from %s with %s viewers", event["tags"]["display-name"], event["tags"]["msg-param-viewerCount"])
    except Exception:
        twitch_log.warning(event)


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
        twitch_log.debug(f"invoke_chat_command: {cmd.text[1:]} {resp.response}")
        await cmd.reply(resp.response)


async def modify_channel_information(cmd: ChatCommand):
    pass


async def run():
    app_config = sqldb.get_oauth_client(APIType.Twitch, 2)
    app_token = sqldb.get_bot_oauth_token(APIType.Twitch, 2)
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
        await twitch.set_user_authentication(app_token.access_token, USER_SCOPE, app_token.refresh_token)
    except (InvalidTokenException, MissingScopeException) as e:
        auth = UserAuthenticator(twitch, USER_SCOPE)
        token, refresh_token = await auth.authenticate()  # type: ignore
        me = await first(twitch.get_users())
        app_token.user_id = me.id
        app_token.client_credential_id = app_config.credential_id
        app_token.access_token = token
        app_token.refresh_token = refresh_token
        app_token = sqldb.merge(app_token)
        await twitch.set_user_authentication(app_token.access_token, USER_SCOPE, app_token.refresh_token)

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
        twitch_log.debug(f"register command: {cmd} in {login_id_map.get(str(twitch_id))} is {succ}")
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
        twitch_log.debug(f"eventsub:{user.login}")
        try:
            subscription_id = await eventsub.listen_stream_online(user.id, on_stream_online)
            await asyncio.sleep(1)
        except EventSubSubscriptionError as e:
            twitch_log.warning(f"Error subscribing stream online: {e}")
        except EventSubSubscriptionTimeout:
            twitch_log.warning(f"Error subscribing stream online: timeout.")

        try:
            subscription_id = await eventsub.listen_stream_offline(user.id, on_stream_offline)
            await asyncio.sleep(1)
        except EventSubSubscriptionError as e:
            twitch_log.warning(f"Error subscribing stream offline: {e}")
        except EventSubSubscriptionTimeout:
            twitch_log.warning(f"Error subscribing stream offline: timeout.")

        try:
            subscription_id = await eventsub.listen_channel_raid(on_channel_raid, to_broadcaster_user_id=user.id)
            await asyncio.sleep(1)
        except EventSubSubscriptionError as e:
            twitch_log.warning(f"Error subscribing channel raid: {e}")
        except EventSubSubscriptionTimeout:
            twitch_log.warning(f"Error subscribing channel raid: timeout.")

        twitch_log.debug(f"eventsub:{user.login} done.")

        if not chat.is_mod(user.login):
            continue

        try:
            twitch_log.debug("listening to channel follow")
            subscription_id = await eventsub.listen_channel_follow_v2(user.id, me.id, on_follow)
            twitch_log.debug(f"subscription_id: {subscription_id}")
            await asyncio.sleep(1)
        except EventSubSubscriptionError as e:
            twitch_log.warning(f"Error subscribing to channel follow: {e}")
        except EventSubSubscriptionTimeout:
            twitch_log.warning(f"Error subscribing to channel follow: timeout.")

        try:
            twitch_log.debug("listening to channel points custom reward redemption add")
            subscription_id = await eventsub.listen_channel_points_custom_reward_redemption_add(user.id, on_channel_points_custom_reward_redemption_add)
            twitch_log.debug(f"subscription_id: {subscription_id}")
            await asyncio.sleep(1)
        except EventSubSubscriptionError as e:
            twitch_log.warning(f"Error subscribing to channel points custom reward redemption add: {e}")
        except EventSubSubscriptionTimeout:
            twitch_log.warning(f"Error subscribing to channel points custom reward redemption add: timeout.")

        try:
            twitch_log.debug("listening to channel points custom reward redemption update")
            subscription_id = await eventsub.listen_channel_points_custom_reward_redemption_update(user.id, on_channel_points_custom_reward_redemption_update)
            twitch_log.debug(f"subscription_id: {subscription_id}")
            await asyncio.sleep(1)
        except EventSubSubscriptionError as e:
            twitch_log.warning(f"Error subscribing to channel points custom reward redemption update: {e}")
        except EventSubSubscriptionTimeout:
            twitch_log.warning(f"Error subscribing to channel points custom reward redemption update: timeout.")

        try:
            twitch_log.debug("listening to channel subscribe")
            subscription_id = await eventsub.listen_channel_subscribe(user.id, on_channel_subscribe)
            twitch_log.debug(f"subscription_id: {subscription_id}")
            await asyncio.sleep(1)
        except EventSubSubscriptionError as e:
            twitch_log.warning(f"Error subscribing to channel subscribe: {e}")
        except EventSubSubscriptionTimeout:
            twitch_log.warning(f"Error subscribing to channel subscribe: timeout.")

        try:
            twitch_log.debug("listening to channel subscription message")
            subscription_id = await eventsub.listen_channel_subscription_message(user.id, on_channel_subscription_message)
            twitch_log.debug(f"subscription_id: {subscription_id}")
            await asyncio.sleep(1)
        except EventSubSubscriptionError as e:
            twitch_log.warning(f"Error subscribing to channel subscription message: {e}")
        except EventSubSubscriptionTimeout:
            twitch_log.warning(f"Error subscribing to channel subscription message: timeout.")

        try:
            twitch_log.debug("listening to channel subscription gift")
            subscription_id = await eventsub.listen_channel_subscription_gift(user.id, on_channel_subscription_gift)
            twitch_log.debug(f"subscription_id: {subscription_id}")
            await asyncio.sleep(1)
        except EventSubSubscriptionError as e:
            twitch_log.warning(f"Error subscribing to channel subscription gift: {e}")
        except EventSubSubscriptionTimeout:
            twitch_log.warning(f"Error subscribing to channel subscription gift: timeout.")

        # try:
        #     twitch_log.debug("listening to channel poll begin")
        #     await eventsub.listen_channel_poll_begin(user.id, on_channel_poll_begin)
        # except EventSubSubscriptionError as e:
        #     twitch_log.warning(f"Error subscribing to channel poll begin: {e}")

        # try:
        #     twitch_log.debug("listening to channel prediction begin")
        #     await eventsub.listen_channel_prediction_begin(user.id, on_channel_prediction_begin)
        # except EventSubSubscriptionError as e:
        #     twitch_log.warning(f"Error subscribing to channel prediction begin: {e}")

        try:
            twitch_log.debug("listening to channel prediction end")
            subscription_id = await eventsub.listen_channel_prediction_end(user.id, on_channel_prediction_end)
            twitch_log.debug(f"subscription_id: {subscription_id}")
        except EventSubSubscriptionError as e:
            twitch_log.warning(f"Error subscribing to channel prediction end: {e}")
        except EventSubSubscriptionTimeout:
            twitch_log.warning(f"Error subscribing to channel prediction end: timeout.")

        twitch_log.debug(f"eventsub for {user.login}(mod) done.")

    return chat, twitch, eventsub


class TwitchBotThread(BaseThread):
    def __init__(self):
        super().__init__(name="TwitchBotThread")
        self.chat: Chat = None
        self.twitch: Twitch = None
        self.eventsub: EventSubWebhook = None

    def run(self):
        self.chat, self.twitch, self.eventsub = asyncio.run(run())
        self._stop_event.wait()
        asyncio.run(self.cleanup())

    async def cleanup(self):
        """安全地清理所有資源"""
        try:
            if self.eventsub:
                await self.eventsub.stop()
        except Exception as e:
            twitch_log.warning(f"Error stopping eventsub: {e}")

        try:
            if self.twitch:
                await self.twitch.close()
        except Exception as e:
            twitch_log.warning(f"Error closing twitch: {e}")

        try:
            if self.chat:
                self.chat.stop()
        except Exception as e:
            twitch_log.warning(f"Error stopping chat: {e}")


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
