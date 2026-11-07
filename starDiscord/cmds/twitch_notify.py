"""Twitch bot（另一個 process）經 messaging bus 送來的通知，轉成 Discord 訊息。"""

import logging
from dataclasses import dataclass

import discord

from sentry_bootstrap import capture_message_safe
from starlib import BotEmbed, Jsondb, sclient
from starlib.messaging import Delivery, get_bus
from starlib.messaging.events.twitch_activity import (
    TwitchPredictionResultEvent,
    TwitchRaidEvent,
    TwitchRedemptionEvent,
    TwitchSubscribeEvent,
    TwitchSubscriptionMessageEvent,
    TwitchWhisperEvent,
)
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
        for event_cls, handler in self._handlers():
            bus.subscribe(event_cls, handler, loop=bot.loop)

    def _handlers(self):
        return (
            (TwitchFollowEvent, self.on_follow),
            (TwitchRaidEvent, self.on_raid),
            (TwitchSubscribeEvent, self.on_subscribe),
            (TwitchSubscriptionMessageEvent, self.on_subscription_message),
            (TwitchRedemptionEvent, self.on_redemption),
            (TwitchPredictionResultEvent, self.on_prediction_result),
            (TwitchWhisperEvent, self.on_whisper),
        )

    def cog_unload(self) -> None:
        bus = get_bus()
        for event_cls, handler in self._handlers():
            bus.unsubscribe(event_cls, handler)

    def _action_channel(self, twitch_id: str) -> discord.abc.Messageable | None:
        """通知頻道；沒設定或頻道不存在回傳 None（後者 resolve_action_channel 已記 log 與 Sentry）。"""
        channel = resolve_action_channel(self.bot, twitch_id)
        if isinstance(channel, NotConfigured | ChannelMissing):
            return None
        return channel

    def _default_channel(self) -> discord.abc.Messageable | None:
        channel = self.bot.get_channel(DEFAULT_TWITCH_CHANNEL)
        if channel is None:
            log.warning("Twitch 預設通知頻道不存在", extra={"channel_id": DEFAULT_TWITCH_CHANNEL})
        return channel  # type: ignore[return-value]

    async def on_follow(self, event: TwitchFollowEvent, delivery: Delivery) -> None:
        channel = self._action_channel(event.broadcaster_id)
        if channel is None:
            return
        await channel.send(f"{event.follower_name}({event.follower_login}) 正在追隨 {event.broadcaster_name}!")

    async def on_raid(self, event: TwitchRaidEvent, delivery: Delivery) -> None:
        channel = self._action_channel(event.to_broadcaster_id)
        if channel is None:
            return
        await channel.send(f"{event.from_broadcaster_name} 帶了 {event.viewers} 位觀眾降落在 {event.to_broadcaster_name} 的頻道!")

    async def on_subscribe(self, event: TwitchSubscribeEvent, delivery: Delivery) -> None:
        channel = self._action_channel(event.broadcaster_id)
        if channel is None:
            return
        await channel.send(f"感謝 {event.user_name} 的訂閱！")

    async def on_subscription_message(self, event: TwitchSubscriptionMessageEvent, delivery: Delivery) -> None:
        channel = self._action_channel(event.broadcaster_id)
        if channel is None:
            return
        # 累積月數為 None（訂閱者不分享）時省略含它的句子，不印 None
        thanks = f"感謝 {event.user_name} 的訂閱！"
        texts = [f"{event.user_name} 在 {event.broadcaster_name} 的{event.duration_months}個月 層級{event.tier[0]}訂閱"]
        if event.cumulative_months is not None:
            thanks += f"\n累積訂閱{event.cumulative_months}個月！"
            texts.append(f"他已經訂閱 {event.cumulative_months} 個月了")
        if event.message is not None:
            texts.append(f"訊息：{event.message}")
        # 兩則依序送出，不能拆成兩個事件
        await channel.send(thanks)
        await channel.send("\n".join(texts))

    async def on_redemption(self, event: TwitchRedemptionEvent, delivery: Delivery) -> None:
        channel = self._action_channel(event.broadcaster_id)
        if channel is None:
            return
        text = f"{event.user_name}({event.user_login}) 兌換了 {event.reward_title}!"
        if event.user_input:
            text += f" ({event.user_input})"
        await channel.send(text)

    async def on_prediction_result(self, event: TwitchPredictionResultEvent, delivery: Delivery) -> None:
        channel = self._default_channel()
        if channel is None:
            return
        embed = BotEmbed.general(event.broadcaster_name, description=f"{event.title}\n{event.outcome_title} 獲勝！{event.users}個人成功預測")
        await channel.send(embed=embed)

    async def on_whisper(self, event: TwitchWhisperEvent, delivery: Delivery) -> None:
        channel = self._default_channel()
        if channel is None:
            return
        await channel.send(embed=BotEmbed.general(event.user_name, Jsondb.get_picture("twitch_001"), description=event.message))


def setup(bot):
    bot.add_cog(TwitchNotify(bot))
