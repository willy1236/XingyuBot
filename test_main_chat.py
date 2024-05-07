from twitchAPI.twitch import Twitch
from twitchAPI.oauth import UserAuthenticator,refresh_access_token,UserAuthenticationStorageHelper
from twitchAPI.type import AuthScope, ChatEvent,EventSubSubscriptionError
from twitchAPI.chat import Chat, EventData, ChatMessage, ChatSub, ChatCommand, JoinedEvent, LeftEvent, NoticeEvent, WhisperEvent
from twitchAPI.chat.middleware import ChannelRestriction
from twitchAPI.pubsub import PubSub
from twitchAPI.object import eventsub
from twitchAPI.eventsub.websocket import EventSubWebsocket
from twitchAPI.helper import first
from twitchAPI.object.api import TwitchUser
import asyncio,os,json, time
from uuid import UUID
from starcord import Jsondb
from pathlib import PurePath

token = Jsondb.get_token('twitch_chatbot')
APP_ID = token.get('id')
APP_SECRET = token.get('secret')
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
    
    ]
TARGET_CHANNEL = ["sakagawa_0309"]

# pubsub
async def pubsub_channel_points(uuid: UUID, data: dict) -> None:
    print("callback_channel_points:",uuid,data)

async def pubsub_bits(uuid: UUID, data: dict) -> None:
    print("callback_bits:",uuid,data)

async def pubsub_chat_moderator_actions(uuid: UUID, data: dict) -> None:
    print("chat_moderator_actions:",uuid,data)

# eventsub
async def on_follow(data: eventsub.ChannelFollowEvent):
    #await chat.send_message(data.event.broadcaster_user_name,text = f'{data.event.user_name} now follows {data.event.broadcaster_user_name}!')
    print(f'{data.event.user_name} now follows {data.event.broadcaster_user_name}!')

async def on_stream_online(event: eventsub.StreamOnlineEvent):
    print(f'{event.event.broadcaster_user_name} starting stream!')

async def on_stream_offline(event: eventsub.StreamOfflineEvent):
    print(f'{event.event.broadcaster_user_name} ending stream.')

async def on_channel_points_custom_reward_redemption_add(event: eventsub.ChannelPointsCustomRewardRedemptionAddEvent):
    print(f'{event.event.user_name} redeemed {event.event.reward.title}!')
    
async def on_channel_points_custom_reward_redemption_update(event: eventsub.ChannelPointsCustomRewardRedemptionUpdateEvent):
    print(f'{event.event.user_name} updated their redemption of {event.event.reward.title}!')

# this will be called when the event READY is triggered, which will be on bot start
async def on_ready(ready_event: EventData):
    print('Bot is ready for work, joining channels')
    # join our target channel, if you want to join multiple, either call join for each individually
    # or even better pass a list of channels as the argument
    await ready_event.chat.join_room(TARGET_CHANNEL)
    # you can do other bot initialization things in here

# this will be called whenever a message in a channel was send by either the bot OR another user
async def on_message(msg: ChatMessage):
    print(f'in {msg.room.name}, {msg.user.name} said: {msg.text}')

# this will be called whenever someone subscribes to a channel
async def on_sub(sub: ChatSub):
    print(f'New subscription in {sub.room.name}:\\n'
          f'  Type: {sub.sub_plan}\\n'
          f'  Message: {sub.sub_message}')

async def on_bot_joined(event: JoinedEvent):
    await asyncio.sleep(1)
    text = f'Joined bot in {event.room_name}'
    if event.chat.is_mod(event.room_name):
        text += " as mod"
    print(text)
        
async def on_bot_leaved(event: LeftEvent):
    print(f'Leaved bot in {event.room_name}')

async def on_server_notice(event: NoticeEvent):
    print(f'Notice from server: {event.message} in {event.room.name}')

async def on_whisper(event: WhisperEvent):
    print(f'Whisper from {event.user.name}: {event.message}')

async def on_raid(event:dict):
    print(f'Raid from {event["from_broadcaster_user_name"]} with {event["viewers"]} viewers')

# this will be called whenever the !reply command is issued
async def test_command(cmd: ChatCommand):
    if len(cmd.parameter) == 0:
        await cmd.reply('you did not tell me what to reply with')
    else:
        await cmd.reply(f'{cmd.user.name}: {cmd.parameter}')

# this is where we set up the bot
async def run():
    # set up twitch api instance and add user authentication with some scopes
    twitch = await Twitch(APP_ID, APP_SECRET)
    auth = UserAuthenticator(twitch, USER_SCOPE)
    
    # 使用自帶的函式處理token
    helper = UserAuthenticationStorageHelper(twitch, USER_SCOPE, storage_path=PurePath('./database/twitch_token.json'))
    await helper.bind()

    # if os.path.exists('database/twitch_token.json'):
    #     with open('database/twitch_token.json','r') as IOtoken:
    #         jtoken = json.load(IOtoken)
    #         token = jtoken['token']
    #         refresh_token = jtoken['refresh_token']
    #         #token, refresh_token = await refresh_access_token(refresh_token, APP_ID, APP_SECRET)
    # else:
    #     #token, refresh_token = await auth.authenticate()
        

    # await twitch.set_user_authentication(token, USER_SCOPE, refresh_token)
    me = await first(twitch.get_users())
    target_user = await first(twitch.get_users(logins=TARGET_CHANNEL))
    users = [user async for user in twitch.get_users(logins=TARGET_CHANNEL)]

    # dict = {
    #     "token": token,
    #     "refresh_token": refresh_token
    # }
    # with open('database/twitch_token.json','w') as IOtoken:
    #     json.dump(dict,IOtoken)


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
        uuid3 = await pubsub.listen_chat_moderator_actions(me.id, user.id, pubsub_bits)
    pubsub.start()
    # you can either start listening before or after you started pubsub.
    

    # create eventsub websocket instance and start the client.
    eventsub = EventSubWebsocket(twitch)
    eventsub.start()
    # subscribing to the desired eventsub hook for our user
    # the given function (in this example on_follow) will be called every time this event is triggered
    # the broadcaster is a moderator in their own channel by default so specifying both as the same works in this example
    # We have to subscribe to the first topic within 10 seconds of eventsub.start() to not be disconnected.
    for user in users:
        await eventsub.listen_stream_online(user.id, on_stream_online)
        await eventsub.listen_stream_offline(user.id, on_stream_offline)
        if chat.is_mod(user.login):
            await eventsub.listen_channel_follow_v2(user.id, me.id, on_follow)
    
            await eventsub.listen_channel_points_custom_reward_redemption_add(user.id, on_channel_points_custom_reward_redemption_add)
    await eventsub.listen_channel_points_custom_reward_redemption_update(me.id, on_channel_points_custom_reward_redemption_update)

    # we are done with our setup, lets start this bot up!
    return chat, twitch
    
if __name__ == '__main__':
    # lets run our setup
    chat, twitch = asyncio.run(run())
    chat:Chat

    # lets run till we press enter in the console
    try:
        input('press ENTER to stop\n')
    finally:
        # now we can close the chat bot and the twitch api client
        chat.stop()
        asyncio.run(twitch.close())
        