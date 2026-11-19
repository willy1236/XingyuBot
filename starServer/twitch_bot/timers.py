"""計時訊息（W-06 實作）。這裡先定好介面，讓 events.py、commands.py 與 run() 之後不必再為它改動。"""

from twitchAPI.chat import Chat


def start(chat: Chat) -> None:
    """Twitch bot 初始化完成後呼叫一次。"""


def stop() -> None:
    """Twitch bot 收尾時呼叫。"""


async def on_stream_online(twitch_id: int) -> None:
    """確認頻道開台後呼叫。"""


async def on_stream_offline(twitch_id: int) -> None:
    """頻道下播時呼叫。"""


async def on_chat_message(twitch_id: int, is_bot: bool) -> None:
    """頻道收到一則聊天室訊息時呼叫；is_bot 表示發言者是 bot 自己。"""
