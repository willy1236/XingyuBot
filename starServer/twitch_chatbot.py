import asyncio
from pathlib import PurePath
from re import A
from typing import TYPE_CHECKING
from uuid import UUID

from twitchAPI.chat import (Chat, ChatCommand, ChatMessage, ChatSub, EventData,
                            JoinedEvent, LeftEvent, NoticeEvent, WhisperEvent)
from twitchAPI.chat.middleware import ChannelRestriction
from twitchAPI.eventsub.webhook import EventSubWebhook
from twitchAPI.eventsub.websocket import EventSubWebsocket
from twitchAPI.helper import first
from twitchAPI.oauth import (UserAuthenticationStorageHelper,
                             UserAuthenticator, refresh_access_token,
                             validate_token)
from twitchAPI.object import eventsub
from twitchAPI.twitch import Twitch, InvalidTokenException, MissingScopeException
from twitchAPI.type import (AuthScope, ChatEvent, EventSubSubscriptionError,
                            EventSubSubscriptionTimeout)

from starlib import BaseThread, BotEmbed, Jsondb, sclient, sqldb, twitch_log
from starlib.instance import tw_api
from starlib.types import NotifyCommunityType, APIType
from starlib.models.mysql import TwitchChatCommand

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

TARGET_CHANNEL = sclient.sqldb.get_bot_join_channel_all()
TARGET_CHANNEL_IDS = [str(i) for i in TARGET_CHANNEL.keys()]

# eventsub
async def on_follow(event: eventsub.ChannelFollowEvent):
    #await chat.send_message(data.event.broadcaster_user_name,text = f'{data.event.user_name} now follows {data.event.broadcaster_user_name}!')
    twitch_log.info(f'{event.event.user_name}({event.event.user_login}) now follows {event.event.broadcaster_user_name}!')
    action_channel_id = TARGET_CHANNEL.get(int(event.event.broadcaster_user_id))
    if action_channel_id and sclient.bot:
        sclient.bot.send_message(action_channel_id, embed=BotEmbed.simple("新追隨",f'{event.event.user_name}({event.event.user_login}) 正在追隨 {event.event.broadcaster_user_name}!'))

async def on_stream_online(event: eventsub.StreamOnlineEvent):
    twitch_log.info(f'{event.event.broadcaster_user_name} starting stream!')

    live = tw_api.get_lives(event.event.broadcaster_user_id)[event.event.broadcaster_user_id]
    action_channel_id = TARGET_CHANNEL.get(int(event.event.broadcaster_user_id))
    if action_channel_id:
        await chat.send_message(event.event.broadcaster_user_login, f'{event.event.broadcaster_user_name} 正在直播 {live.game_name}! {live.title}')

    if sclient.bot:
        sclient.bot.send_message(content=f'{event.event.broadcaster_user_name} 正在直播 {live.game_name}!')
        is_live = bool(sclient.sqldb.get_community_cache(NotifyCommunityType.TwitchLive, event.event.broadcaster_user_id))
        twitch_log.debug(f'{event.event.broadcaster_user_name} is live: {is_live}')
        if not is_live:
            profile_image_url = tw_api.get_user_by_id(event.event.broadcaster_user_id).profile_image_url
            embed = live.embed(profile_image_url)
            asyncio.run_coroutine_threadsafe(sclient.bot.send_notify_communities(embed, NotifyCommunityType.TwitchLive, event.event.broadcaster_user_id), sclient.bot.loop)
            sclient.sqldb.set_community_cache(NotifyCommunityType.TwitchLive, event.event.broadcaster_user_id, live.started_at)

async def on_stream_offline(event: eventsub.StreamOfflineEvent):
    twitch_log.info(f'{event.event.broadcaster_user_name} ending stream.')
    if sclient.bot:
        sclient.bot.send_message(content=f'{event.event.broadcaster_user_name} ending stream.')
        
        is_live = bool(sclient.sqldb.get_community_cache(NotifyCommunityType.TwitchLive, event.event.broadcaster_user_id))
        if is_live:
            sclient.sqldb.set_community_cache(NotifyCommunityType.TwitchLive, event.event.broadcaster_user_id, None)

async def on_channel_points_custom_reward_redemption_add(event: eventsub.ChannelPointsCustomRewardRedemptionAddEvent):
    text = f'{event.event.user_name}({event.event.user_login}) 兌換了 {event.event.reward.title}!'
    if event.event.user_input:
        text += f' ({event.event.user_input})'
    twitch_log.info(text)
    action_channel_id = TARGET_CHANNEL.get(int(event.event.broadcaster_user_id))
    if action_channel_id and sclient.bot:
        sclient.bot.send_message(action_channel_id, embed=BotEmbed.simple("兌換自訂獎勵",text))
    
async def on_channel_points_custom_reward_redemption_update(event: eventsub.ChannelPointsCustomRewardRedemptionUpdateEvent):
    twitch_log.info(f"{event.event.user_name}'s redemption of {event.event.reward.title} has been updated to {event.event.status}!")
    
async def on_channel_raid(event:eventsub.ChannelRaidEvent):
    twitch_log.info(f"{event.event.from_broadcaster_user_name} 帶了 {event.event.viewers} 位觀眾來 {event.event.to_broadcaster_user_name} 的頻道！")
    action_channel_id = TARGET_CHANNEL.get(int(event.event.to_broadcaster_user_id))
    if action_channel_id:
        await chat.send_message(event.event.to_broadcaster_user_login, f"{event.event.from_broadcaster_user_name} 帶了 {event.event.viewers} 位觀眾降落在 {event.event.to_broadcaster_user_name} 的頻道！")
        
        if sclient.bot:
            sclient.bot.send_message(action_channel_id, embed=BotEmbed.simple("揪團", f"{event.event.from_broadcaster_user_name} 帶了 {event.event.viewers} 位觀眾降落在 {event.event.to_broadcaster_user_name} 的頻道!"))

async def on_channel_subscribe(event: eventsub.ChannelSubscribeEvent):
    twitch_log.info(f"{event.event.user_name} 在 {event.event.broadcaster_user_name} 的層級{event.event.tier[0]}新訂閱")
    action_channel_id = TARGET_CHANNEL.get(int(event.event.broadcaster_user_id))
    if action_channel_id and not event.event.is_gift:
        # await chat.send_message(event.event.broadcaster_user_login, f"感謝 {event.event.user_name} 的訂閱！")
        if sclient.bot:
            sclient.bot.send_message(embed=BotEmbed.simple("subscribe", f"感謝 {event.event.user_name} 的訂閱！"))

async def on_channel_subscription_message(event: eventsub.ChannelSubscriptionMessageEvent):
    texts = [
        f"{event.event.user_name} 在 {event.event.broadcaster_user_name} 的{event.event.duration_months}個月 層級{event.event.tier[0]}訂閱",
        f"他已經訂閱 {event.event.cumulative_months} 個月了",
    ]
    if event.event.message:
        texts.append(f"訊息：{event.event.message.text}")
    
    for text in texts:
        twitch_log.info(text)
    
    action_channel_id = TARGET_CHANNEL.get(int(event.event.broadcaster_user_id))
    if action_channel_id:
        chat_text = f"感謝 {event.event.user_name} 的訂閱！"
        if event.event.cumulative_months:
            chat_text += f"累積訂閱{event.event.cumulative_months}個月！"
        await chat.send_message(event.event.broadcaster_user_login, chat_text)

        if sclient.bot:
            sclient.bot.send_message(action_channel_id, embed=BotEmbed.simple("新訂閱","\n".join(texts)))
            sclient.bot.send_message(embed=BotEmbed.simple("subscription_message", "\n".join(texts)))

async def on_channel_subscription_gift(event: eventsub.ChannelSubscriptionGiftEvent):
    twitch_log.info(f"{event.event.user_name} 在 {event.event.broadcaster_user_name} 送出的{event.event.total}份層級{event.event.tier[0]}訂閱")
    action_channel_id = TARGET_CHANNEL.get(int(event.event.broadcaster_user_id))
    if action_channel_id and not event.event.is_anonymous:
        await chat.send_message(event.event.broadcaster_user_login, f"感謝 {event.event.user_name} 送出的{event.event.total}份訂閱！")

async def on_channel_poll_begin(event: eventsub.ChannelPollBeginEvent):
    twitch_log.info(f"{event.event.broadcaster_user_name} 開始了投票：{event.event.title}")
    if sclient.bot:
        sclient.bot.send_message(embed=BotEmbed.general(event.event.broadcaster_user_name,description=f"{event.event.title}\n{event.event.choices}"))

async def on_channel_prediction_begin(event: eventsub.ChannelPredictionEvent):
    twitch_log.info(f"{event.event.broadcaster_user_name} 開始了預測：{event.event.title}\n{event.event.outcomes[0].title} V.S. {event.event.outcomes[1].title}")
    if sclient.bot:
        sclient.bot.send_message(embed=BotEmbed.general(event.event.broadcaster_user_name,description=f"{event.event.title}\n{event.event.outcomes[0].title} V.S. {event.event.outcomes[1].title}"))

async def on_channel_prediction_end(event: eventsub.ChannelPredictionEndEvent):
    if event.event.status == "resolved":
        twitch_log.info(f"{event.event.broadcaster_user_name} 結束了預測：{event.event.title}")
        for outcome in event.event.outcomes:
            if outcome.id == event.event.winning_outcome_id:
                twitch_log.info(f"{outcome.title} ({outcome.color}) 獲勝！{outcome.users}個人成功預測")
                if sclient.bot:
                    sclient.bot.send_message(embed=BotEmbed.general(event.event.broadcaster_user_name,description=f"{event.event.title}\n{outcome.title} 獲勝！{outcome.users}個人成功預測"))
    else:
        twitch_log.info(f"{event.event.broadcaster_user_name} 取消了預測：{event.event.title}")


# bot
async def on_ready(ready_event: EventData):
    twitch_log.info(f'Bot is ready as {ready_event.chat.username}, joining channels')
    # join our target channel, if you want to join multiple, either call join for each individually
    # or even better pass a list of channels as the argument
    if users_login:
        await ready_event.chat.join_room(users_login)

# this will be called whenever a message in a channel was send by either the bot OR another user
async def on_message(msg: ChatMessage):
    twitch_log.info(f'in {msg.room.name}, {msg.user.name} said: {msg.text}')

async def on_sub(sub: ChatSub):
    twitch_log.info(f'New subscription in {sub.room.name}:')
    twitch_log.info(f'Type: {sub.sub_plan_name}')
    twitch_log.info(f'Message: {sub.sub_message}')
    twitch_log.info(f"System message: {sub.system_message}")

async def on_bot_joined(event: JoinedEvent):
    await asyncio.sleep(1)
    text = f'Joined bot in {event.room_name}'
    if event.chat.is_mod(event.room_name):
        text += " as mod"
    twitch_log.info(text)
        
async def on_bot_leaved(event: LeftEvent):
    twitch_log.info(f'Leaved bot in {event.room_name}')
    

async def on_server_notice(event: NoticeEvent):
    if event.room:
        twitch_log.info(f'Notice from server: {event.message} in {event.room.name}')
    else:
        twitch_log.info(f'Notice from server: {event.message}')

async def on_whisper(event: WhisperEvent):
    twitch_log.info(f'Whisper from {event.user.name}: {event.message}')
    if sclient.bot:
        sclient.bot.send_message(embed=BotEmbed.general(event.user.name, Jsondb.get_picture("twitch_001"),description=event.message))

async def on_raid(event:dict):
    print(event)
    try:
        twitch_log.info(f'Raid from {event["tags"]["display-name"]} with {event["tags"]["msg-param-viewerCount"]} viewers')
    except:
        twitch_log.info(event)

# this will be called whenever the !reply command is issued
async def test_command(cmd: ChatCommand):
    if len(cmd.parameter) == 0:
        await cmd.reply('you did not tell me what to reply with')
    else:
        await cmd.reply(f'{cmd.user.name}: {cmd.parameter}')

async def add_chat_command(cmd: ChatCommand):
    if len(cmd.parameter) < 2:
        await cmd.reply('用法：!add_command <指令> <回覆>')
    else:
        sclient.sqldb.merge(TwitchChatCommand(twitch_id=cmd.source_room_id, command=cmd.parameter[0], response=" ".join(cmd.parameter[1:])))
        await cmd.reply(f'已新增指令：{cmd.parameter[0]}')

async def remove_chat_command(cmd: ChatCommand):
    if len(cmd.parameter) < 1:
        await cmd.reply('用法：!remove_command <指令>')
    else:
        sclient.sqldb.delete(TwitchChatCommand(twitch_id=cmd.source_room_id, command=cmd.parameter[0]))
        await cmd.reply(f'已移除指令：{cmd.parameter[0]}')

async def list_chat_command(cmd: ChatCommand):
    if len(cmd.parameter) < 1:
        commands = sclient.sqldb.list_chat_command_by_channel(cmd.source_room_id)
        if commands:
            await cmd.reply(f'指令列表：\n{", ".join([i.name for i in commands])}')
        else:
            await cmd.reply('沒有設定指令')
    else:
        command = sclient.sqldb.get_chat_command(cmd.parameter[0], cmd.source_room_id)
        if command:
            await cmd.reply(f'{command.name}：{command.response}')
        else:
            await cmd.reply(f'{cmd.parameter[0]} 不存在')

async def modify_channel_information(cmd: ChatCommand):
    pass

async def run():
    jtoken = sqldb.get_bot_token(APIType.Twitch)
    APP_ID = jtoken.client_id
    APP_SECRET = jtoken.client_secret

    # validate_data = await validate_token(token)
    # if validate_data.get("client_id") != APP_ID:
    #     token, refresh_token = await refresh_access_token(refresh_token, APP_ID, APP_SECRET)
    #     jtoken['token'] = token
    #     jtoken['refresh'] = refresh_token
    
    # set up twitch api instance and add user authentication with some scopes
    twitch = await Twitch(APP_ID, APP_SECRET)
    try:
        await twitch.set_user_authentication(jtoken.access_token, USER_SCOPE, jtoken.refresh_token)
    except (InvalidTokenException, MissingScopeException) as e:
        auth = UserAuthenticator(twitch, USER_SCOPE)
        token, refresh_token = await auth.authenticate() # type: ignore
        jtoken.access_token = token
        jtoken.refresh_token = refresh_token
        sqldb.merge(jtoken)
        await twitch.set_user_authentication(jtoken.access_token, USER_SCOPE, jtoken.refresh_token)

    # 使用自帶的函式處理token
    # helper = UserAuthenticationStorageHelper(twitch, USER_SCOPE)
    # await helper.bind()

    me = await first(twitch.get_users())
    users = [user async for user in twitch.get_users(user_ids=TARGET_CHANNEL_IDS)]
    global users_login
    users_login = [user.login for user in users]

    # create chat instance
    global chat
    chat:"Chat" = await Chat(twitch)

    # register the handlers for the events you want
    chat.register_event(ChatEvent.READY, on_ready)
    chat.register_event(ChatEvent.MESSAGE, on_message)
    chat.register_event(ChatEvent.SUB, on_sub)
    chat.register_event(ChatEvent.JOINED, on_bot_joined)
    chat.register_event(ChatEvent.LEFT, on_bot_leaved)
    chat.register_event(ChatEvent.NOTICE, on_server_notice)
    chat.register_event(ChatEvent.WHISPER, on_whisper)
    chat.register_event(ChatEvent.RAID, on_raid)
    
    #chat.register_command_middleware(ChannelRestriction(allowed_channel=['sakagawa_0309']))
    chat.register_command_middleware(ChannelRestriction(allowed_channel=['willy1236owo']))
    # you can directly register commands and their handlers, this will register the !reply command
    # chat.register_command('reply', test_command)
    chat.register_command("add_command", add_chat_command)
    chat.register_command("remove_command", remove_chat_command)
    chat.register_command("list_command", list_chat_command)
    # TODO: modify_channel_information
    
    chat.start()
    await asyncio.sleep(5)

    eventsub = EventSubWebhook(jtoken.callback_uri, 14001, twitch)
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
        
    sclient.twitch = twitch
    return chat, twitch
class TwitchBotThread(BaseThread):
    def __init__(self):
        super().__init__(name='TwitchBotThread')

    def run(self):
        asyncio.run(run())
        self._stop_event.wait()
        chat.stop()
        asyncio.run(twitch.close())

if __name__ == '__main__':
    chat, twitch = asyncio.run(run())
    chat:Chat
    twitch:Twitch

    try:
        input('press ENTER to stop\n')
    finally:
        chat.stop()
        asyncio.run(twitch.close())
        