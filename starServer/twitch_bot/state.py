"""Twitch bot 各模組共用的執行期狀態；import 時不查 DB，由 run() 開頭的 load_join_channels() 填入。"""

from twitchAPI.chat import Chat
from twitchAPI.eventsub.webhook import EventSubWebhook
from twitchAPI.twitch import Twitch

from starlib.database import sqldb

join_channels: dict = {}
TARGET_CHANNEL: dict = {}
TARGET_CHANNEL_IDS: list[str] = []


def load_join_channels() -> None:
    global join_channels, TARGET_CHANNEL, TARGET_CHANNEL_IDS
    join_channels = sqldb.get_bot_join_channel_all()
    TARGET_CHANNEL = {twitch_id: data.action_channel_id for twitch_id, data in join_channels.items()}
    TARGET_CHANNEL_IDS = [str(i) for i in TARGET_CHANNEL.keys()]


chat: Chat
# run() 建立的 Twitch API 物件，handler 用它查 Helix
twitch: Twitch
# run() 建立的 EventSub webhook 與 bot 自己的使用者 ID
eventsub: EventSubWebhook
bot_user_id: str
