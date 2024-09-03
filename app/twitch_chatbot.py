import asyncio
import threading
from pathlib import PurePath
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
from twitchAPI.pubsub import PubSub
from twitchAPI.twitch import Twitch
from twitchAPI.type import AuthScope, ChatEvent, EventSubSubscriptionError

from starlib import BotEmbed, Jsondb, sclient, twitch_log

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
    AuthScope.WHISPERS_EDIT,
    ]

TARGET_CHANNEL = ["sakagawa_0309", "willy1236owo", "niantt_"]

# pubsub (may be deprecated in the future)
async def pubsub_channel_points(uuid: UUID, data: dict) -> None:
    twitch_log.info("callback_channel_points:",uuid,data)

async def pubsub_bits(uuid: UUID, data: dict) -> None:
    twitch_log.info("callback_bits:",uuid,data)

async def pubsub_chat_moderator_actions(uuid: UUID, data: dict) -> None:
    twitch_log.info("chat_moderator_actions:",uuid,data)

# eventsub
async def on_follow(event: eventsub.ChannelFollowEvent):
    #await chat.send_message(data.event.broadcaster_user_name,text = f'{data.event.user_name} now follows {data.event.broadcaster_user_name}!')
    twitch_log.info(f'{event.event.user_name}({event.event.user_login}) now follows {event.event.broadcaster_user_name}!')
    if event.event.broadcaster_user_login == TARGET_CHANNEL[0] and sclient.bot:
        sclient.bot.twitchbot_send_message(1237412404980355092, embed=BotEmbed.simple("新追隨",f'{event.event.user_name}({event.event.user_login}) 正在追隨 {event.event.broadcaster_user_name}!'))
        

async def on_stream_online(event: eventsub.StreamOnlineEvent):
    twitch_log.info(f'{event.event.broadcaster_user_name} starting stream!')
    if sclient.bot:
        sclient.bot.twitchbot_send_message(content=f'{event.event.broadcaster_user_name} starting {event.event.type}!')
        

async def on_stream_offline(event: eventsub.StreamOfflineEvent):
    twitch_log.info(f'{event.event.broadcaster_user_name} ending stream.')
    if sclient.bot:
        sclient.bot.twitchbot_send_message(content=f'{event.event.broadcaster_user_name} ending stream.')

async def on_channel_points_custom_reward_redemption_add(event: eventsub.ChannelPointsCustomRewardRedemptionAddEvent):
    text = f'{event.event.user_name}({event.event.user_login}) 兌換了 {event.event.reward.title}!'
    if event.event.user_input:
        text += f' ({event.event.user_input})'
    twitch_log.info(text)
    if event.event.broadcaster_user_login == TARGET_CHANNEL[0] and sclient.bot:
        sclient.bot.twitchbot_send_message(1237412404980355092, embed=BotEmbed.simple("兌換自訂獎勵",text))
    
async def on_channel_points_custom_reward_redemption_update(event: eventsub.ChannelPointsCustomRewardRedemptionUpdateEvent):
    twitch_log.info(f"{event.event.user_name}'s redemption of {event.event.reward.title} has been updated!")
    
async def on_channel_raid(event:eventsub.ChannelRaidEvent):
    twitch_log.info(f"{event.event.from_broadcaster_user_name} 帶了 {event.event.viewers} 位觀眾來 {event.event.to_broadcaster_user_name} 的頻道!")

async def on_channel_subscribe(event: eventsub.ChannelSubscribeEvent):
    twitch_log.info(f"{event.event.user_name} 在 {event.event.broadcaster_user_name} 的層級{event.event.tier[0]}新訂閱")

async def on_channel_subscription_message(event: eventsub.ChannelSubscriptionMessageEvent):
    texts = [
        f"{event.event.user_name} 在 {event.event.broadcaster_user_name} 的{event.event.duration_months}個月 層級{event.event.tier[0]}訂閱",
        f"他已經訂閱 {event.event.cumulative_months} 個月了",
    ]
    if event.event.message:
        texts.append(f"訊息：{event.event.message.text}")
    
    for text in texts:
        twitch_log.info(text)
    
    if event.event.broadcaster_user_login == TARGET_CHANNEL[0] and sclient.bot:
        sclient.bot.twitchbot_send_message(1237412404980355092, embed=BotEmbed.simple("新訂閱","\n".join(texts)))
        await chat.send_message(TARGET_CHANNEL[0], f"感謝{event.event.user_name}的{event.event.duration_months}個月訂閱！")
    

# bot
async def on_ready(ready_event: EventData):
    twitch_log.info(f'Bot is ready as {ready_event.chat.username}, joining channels')
    # join our target channel, if you want to join multiple, either call join for each individually
    # or even better pass a list of channels as the argument
    await ready_event.chat.join_room(TARGET_CHANNEL)

# this will be called whenever a message in a channel was send by either the bot OR another user
async def on_message(msg: ChatMessage):
    twitch_log.info(f'in {msg.room.name}, {msg.user.name} said: {msg.text}')

async def on_sub(sub: ChatSub):
    twitch_log.info(f'New subscription in {sub.room.name}:\nType: {sub.sub_plan_name}\nMessage: {sub.sub_message}')

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
        sclient.bot.twitchbot_send_message(embed=BotEmbed.general(event.user.name,description=event.message))

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

async def run():
    jtoken = Jsondb.get_token("twitch_chatbot")
    APP_ID = jtoken.get('id')
    APP_SECRET = jtoken.get('secret')

    # validate_data = await validate_token(token)
    # if validate_data.get("client_id") != APP_ID:
    #     token, refresh_token = await refresh_access_token(refresh_token, APP_ID, APP_SECRET)
    #     jtoken['token'] = token
    #     jtoken['refresh'] = refresh_token
    #     Jsondb.set_token("twitch_chatbot", jtoken)
    
    # set up twitch api instance and add user authentication with some scopes
    twitch = await Twitch(APP_ID, APP_SECRET)
    auth = UserAuthenticator(twitch, USER_SCOPE)
    #  await twitch.set_user_authentication(token, USER_SCOPE, refresh_token)

    # 使用自帶的函式處理token
    helper = UserAuthenticationStorageHelper(twitch, USER_SCOPE, storage_path=PurePath('./database/twitch_token.json'))
    await helper.bind()

    me = await first(twitch.get_users())
    users = [user async for user in twitch.get_users(logins=TARGET_CHANNEL)]

    # create chat instance
    global chat
    chat = await Chat(twitch)

    # register the handlers for the events you want
    # listen to when the bot is done starting up and ready to join channels
    chat.register_event(ChatEvent.READY, on_ready)
    # listen to chat messages
    chat.register_event(ChatEvent.MESSAGE, on_message)
    # listen to channel subscriptions
    chat.register_event(ChatEvent.SUB, on_sub)
    # there are more events, you can view them all in this documentation
    chat.register_event(ChatEvent.JOINED, on_bot_joined)
    chat.register_event(ChatEvent.LEFT, on_bot_leaved)
    chat.register_event(ChatEvent.NOTICE, on_server_notice)
    chat.register_event(ChatEvent.WHISPER, on_whisper)
    chat.register_event(ChatEvent.RAID, on_raid)
    
    chat.register_command_middleware(ChannelRestriction(allowed_channel=['sakagawa_0309']))
    # you can directly register commands and their handlers, this will register the !reply command
    # chat.register_command('reply', test_command)
    # TODO: modify_channel_information
    
    chat.start()

    # starting up PubSub
    pubsub = PubSub(twitch)
    for user in users:
        uuid1 = await pubsub.listen_channel_points(user.id, pubsub_channel_points)
        uuid2 = await pubsub.listen_bits(user.id, pubsub_bits)
        uuid3 = await pubsub.listen_chat_moderator_actions(me.id, user.id, pubsub_chat_moderator_actions)
    pubsub.start()
    # you can either start listening before or after you started pubsub.
    

    # # create eventsub websocket instance and start the client.
    # eventsub = EventSubWebsocket(twitch)
    # eventsub.start()
    # # subscribing to the desired eventsub hook for our user
    # # the given function (in this example on_follow) will be called every time this event is triggered
    # # the broadcaster is a moderator in their own channel by default so specifying both as the same works in this example
    # # We have to subscribe to the first topic within 10 seconds of eventsub.start() to not be disconnected.
    # for user in users:
    #     await eventsub.listen_stream_online(user.id, on_stream_online)
    #     await eventsub.listen_stream_offline(user.id, on_stream_offline)
    #     if chat.is_mod(user.login):
    #         await eventsub.listen_channel_follow_v2(user.id, me.id, on_follow)
    
    eventsub = EventSubWebhook(jtoken.get('callback_uri'), 14001, twitch)
    # unsubscribe from all old events that might still be there
    # this will ensure we have a clean slate
    await eventsub.unsubscribe_all()
    # start the eventsub client
    eventsub.start()
    for user in users:
        twitch_log.debug(f"eventsub:{user.login}")
        await eventsub.listen_stream_online(user.id, on_stream_online)
        await eventsub.listen_stream_offline(user.id, on_stream_offline)
        await eventsub.listen_channel_raid(on_channel_raid, to_broadcaster_user_id=user.id)
        twitch_log.debug(f"eventsub:{user.login} done.")

        if not chat.is_mod(user.login):
            continue
        
        try:
            twitch_log.debug("listening to channel points custom reward redemption add")
            await eventsub.listen_channel_points_custom_reward_redemption_add(user.id, on_channel_points_custom_reward_redemption_add)
        except EventSubSubscriptionError as e:
            twitch_log.warn(f"Error subscribing to channel points custom reward redemption add: {e}")
        
        try:
            twitch_log.debug("listening to channel points custom reward redemption update")
            await eventsub.listen_channel_points_custom_reward_redemption_update(user.id, on_channel_points_custom_reward_redemption_update)
        except EventSubSubscriptionError as e:
            twitch_log.warn(f"Error subscribing to channel points custom reward redemption update: {e}")

        try:
            twitch_log.debug("listening to channel subscribe")
            await eventsub.listen_channel_subscribe(user.id, on_channel_subscribe)
        except EventSubSubscriptionError as e:
            twitch_log.warn(f"Error subscribing to channel subscribe: {e}")

        try:
            twitch_log.debug("listening to channel subscription message")
            await eventsub.listen_channel_subscription_message(user.id, on_channel_subscription_message)
        except EventSubSubscriptionError as e:
            twitch_log.warn(f"Error subscribing to channel subscription message: {e}")

        try:
            twitch_log.debug("listening to channel follow")
            await eventsub.listen_channel_follow_v2(user.id, me.id, on_follow)
        except EventSubSubscriptionError as e:
            twitch_log.warn(f"Error subscribing to channel follow: {e}")

    sclient.twitch = twitch
    # we are done with our setup, lets start this bot up!
    return chat, twitch
    
async def run_sakagawa():
    USER_SCOPE_SAKAGAWA = [AuthScope.CHANNEL_READ_REDEMPTIONS]
    jtoken = Jsondb.get_token("twitch_sakagawa")
    token = jtoken['token']
    refresh_token = jtoken['refresh']
    client_id = jtoken['client_id']

    validate_data = await validate_token(token)
    if validate_data.get("client_id") != client_id:
        raise ValueError(validate_data)
    
    twitch_sakagawa = await Twitch(client_id, authenticate_app=False)
    await twitch_sakagawa.set_user_authentication(token, USER_SCOPE_SAKAGAWA, refresh_token)
    target_user = await first(twitch_sakagawa.get_users(logins=TARGET_CHANNEL))

    eventsub_sakagawa = EventSubWebsocket(twitch_sakagawa)
    eventsub_sakagawa.start()
    await eventsub_sakagawa.listen_channel_points_custom_reward_redemption_add(target_user.id, on_channel_points_custom_reward_redemption_add)
    twitch_log.debug("listening to channel points custom reward redemption add")
    await eventsub_sakagawa.listen_channel_points_custom_reward_redemption_update(target_user.id, on_channel_points_custom_reward_redemption_update)
    twitch_log.debug("listening to channel points custom reward redemption update")

class TwitchBotThread(threading.Thread):
    if TYPE_CHECKING:
        chat:Chat | None
        twitch:Twitch | None
        
    def __init__(self):
        super().__init__(name='TwitchBotThread')
        self._stop_event = threading.Event()
        self.chat = None
        self.twitch = None

    def run(self):
        chat, twitch = asyncio.run(run())
        self.chat = chat
        self.twitch = twitch
        
        self._stop_event.wait()
        chat.stop()
        asyncio.run(twitch.close())

class SakagawaEventsubThread(threading.Thread):
    def __init__(self):
        super().__init__(name='SakagawaEventsubThread')
        self._stop_event = threading.Event()

    def run(self):
        asyncio.run(run_sakagawa())
        
        self._stop_event.wait()

if __name__ == '__main__':
    # lets run our setup
    chat, twitch = asyncio.run(run())
    chat:Chat
    twitch:Twitch
    asyncio.run(run_sakagawa())
    # auth = UserAuthenticator(twitch, [AuthScope.CHANNEL_READ_REDEMPTIONS])
    # print(auth.return_auth_url())

    # lets run till we press enter in the console
    try:
        input('press ENTER to stop\n')
    finally:
        # now we can close the chat bot and the twitch api client
        chat.stop()
        asyncio.run(twitch.close())
        