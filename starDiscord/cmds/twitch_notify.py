"""Twitch bot（另一個 process）經 messaging bus 送來的通知，轉成 Discord 訊息。"""

import logging
from dataclasses import dataclass

import discord

from sentry_bootstrap import capture_message_safe
from starlib import sclient
from starlib.messaging import Delivery, get_bus
from starlib.messaging.events.twitch_follow import TwitchFollowEvent

from ..extension import Cog_Extension

log = logging.getLogger(__name__)

DEFAULT_TWITCH_CHANNEL = 566533708371329026


@dataclass(frozen=True)
class NotConfigured:
    """這個 Twitch 頻道沒有設定通知頻道。"""


@dataclass(frozen=True)
class ChannelMissing:
    """設定了通知頻道，但 Discord 找不到它。"""


ActionChannel = NotConfigured | ChannelMissing | discord.abc.Messageable


def resolve_action_channel(bot: discord.Bot, twitch_id: str) -> ActionChannel:
    """依 TwitchBotJoinChannel 決定這個 Twitch 頻道的通知要發到哪個 Discord 頻道，設定改了立即生效。"""
    config = sclient.sqldb.get_twitch_join_channel(twitch_id)
    if config is None or not config.action_channel_id:
        return NotConfigured()
    channel = bot.get_channel(config.action_channel_id)
    if channel is None:
        log.warning("Twitch 通知頻道不存在", extra={"twitch_id": twitch_id, "channel_id": config.action_channel_id})
        capture_message_safe(
            f"Twitch 通知頻道不存在：twitch_id={twitch_id} channel_id={config.action_channel_id}",
            level="error",
            tags={"service": "discord", "source": "twitch_notify"},
        )
        return ChannelMissing()
    return channel  # type: ignore[return-value]


class TwitchNotify(Cog_Extension):
    def __init__(self, bot):
        super().__init__(bot)
        # py-cord 沒有 cog_load；__init__ 在載入與 /reload 時都會執行，重複 subscribe 會取代舊 handler
        bus = get_bus()
        bus.subscribe(TwitchFollowEvent, self.on_follow, loop=bot.loop)

    async def on_follow(self, event: TwitchFollowEvent, delivery: Delivery) -> None:
        channel = resolve_action_channel(self.bot, event.broadcaster_id)
        if isinstance(channel, NotConfigured | ChannelMissing):
            return
        await channel.send(f"{event.follower_name}({event.follower_login}) 正在追隨 {event.broadcaster_name}!")


def setup(bot):
    bot.add_cog(TwitchNotify(bot))
