"""Twitch bot 各模組共用的執行期狀態；import 時不查 DB，由 run() 開頭的 load_join_channels() 填入。"""

import asyncio
from datetime import datetime

from twitchAPI.chat import Chat
from twitchAPI.eventsub.webhook import EventSubWebhook
from twitchAPI.twitch import Twitch

from starlib.database import sqldb

# Twitch bot process 的啟動時間，twitch_main 啟動時設定
started_at: datetime | None = None

join_channels: dict = {}
TARGET_CHANNEL: dict = {}
TARGET_CHANNEL_IDS: list[str] = []


def load_join_channels() -> None:
    """讀入全部頻道的設定（join_channels，handler 查通知頻道用）；bot 要加入的只有 state 為 enabled 的頻道。"""
    global join_channels, TARGET_CHANNEL, TARGET_CHANNEL_IDS
    join_channels = sqldb.get_bot_join_channel_all()
    TARGET_CHANNEL = {
        twitch_id: data.action_channel_id for twitch_id, data in join_channels.items() if data.state == "enabled"
    }
    TARGET_CHANNEL_IDS = [str(i) for i in TARGET_CHANNEL.keys()]


chat: Chat
# run() 建立的 Twitch API 物件，handler 用它查 Helix
twitch: Twitch
# run() 建立的 EventSub webhook 與 bot 自己的使用者 ID
eventsub: EventSubWebhook
bot_user_id: str
# Chat 的 event loop：join_room、leave_room 必須在它上面呼叫，RPC 與快取失效的 handler 也跑在這裡；READY 時設定
loop: asyncio.AbstractEventLoop
