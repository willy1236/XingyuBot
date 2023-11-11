from twitchAPI.twitch import Twitch
from twitchAPI.oauth import UserAuthenticator,refresh_access_token,UserAuthenticationStorageHelper
from twitchAPI.type import AuthScope, ChatEvent,EventSubSubscriptionError
from twitchAPI.chat import Chat, EventData, ChatMessage, ChatSub, ChatCommand
from twitchAPI.pubsub import PubSub
from twitchAPI.object.eventsub import ChannelFollowEvent
from twitchAPI.eventsub.websocket import EventSubWebsocket
from twitchAPI.helper import first
from twitchAPI.object.api import TwitchUser
import asyncio,os,json
from uuid import UUID
from starcord import Jsondb

token = Jsondb.get_token('twitch_chatbot')
APP_ID = token.get('id')
APP_SECRET = token.get('secret')
USER_SCOPE = [AuthScope.CHAT_READ, AuthScope.CHAT_EDIT,AuthScope.BITS_READ,AuthScope.USER_EDIT_FOLLOWS,AuthScope.CHANNEL_READ_REDEMPTIONS,AuthScope.MODERATOR_READ_FOLLOWERS]
#TARGET_CHANNEL = ["helper_chatbot","sakagawa_0309"]
TARGET_CHANNEL = "sakagawa_0309"

async def callback_whisper(uuid: UUID, data: dict) -> None:
    print('got callback for UUID ' + str(uuid))
    print(data)

async def on_follow(data: ChannelFollowEvent):
    # our event happend, lets do things with the data we got!
    #await chat.send_message(data.event.broadcaster_user_name,text = f'{data.event.user_name} now follows {data.event.broadcaster_user_name}!')
    print(f'{data.event.user_name} now follows {data.event.broadcaster_user_name}!')

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
    helper = UserAuthenticationStorageHelper(twitch, USER_SCOPE)
    await helper.bind()

    if os.path.exists('database/twitch_token.json'):
        with open('database/twitch_token.json','r') as IOtoken:
            jtoken = json.load(IOtoken)
            token = jtoken['token']
            refresh_token = jtoken['refresh_token']
            #token, refresh_token = await refresh_access_token(refresh_token, APP_ID, APP_SECRET)
    else:
        token, refresh_token = await auth.authenticate()

    dict = {
        "token": token,
        "refresh_token": refresh_token
    }
    with open('database/twitch_token.json','w') as IOtoken:
        json.dump(dict,IOtoken)

    await twitch.set_user_authentication(token, USER_SCOPE, refresh_token)
    me = await first(twitch.get_users())
    user = await first(twitch.get_users(logins=TARGET_CHANNEL))


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

    # you can directly register commands and their handlers, this will register the !reply command
    chat.register_command('reply', test_command)
    
    # starting up PubSub
    pubsub = PubSub(twitch)
    # uuid1 = await pubsub.listen_bits_v1(user.id, callback_whisper)
    await pubsub.listen_channel_points(user.id, callback_whisper)
    pubsub.start()
    # you can either start listening before or after you started pubsub.
    

    # create eventsub websocket instance and start the client.
    eventsub = EventSubWebsocket(twitch)
    eventsub.start()
    # subscribing to the desired eventsub hook for our user
    # the given function (in this example on_follow) will be called every time this event is triggered
    # the broadcaster is a moderator in their own channel by default so specifying both as the same works in this example
    # We have to subscribe to the first topic within 10 seconds of eventsub.start() to not be disconnected.
    try:
        await eventsub.listen_channel_follow_v2(user.id, me.id, on_follow)
    except Exception as e:
        print(e)


    # we are done with our setup, lets start this bot up!
    chat.start()

    # lets run till we press enter in the console
    try:
        input('press ENTER to stop\n')
    finally:
        # now we can close the chat bot and the twitch api client
        chat.stop()
        await twitch.close()


# lets run our setup
asyncio.run(run())