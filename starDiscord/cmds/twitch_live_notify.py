"""Twitch bot（另一個 process）送來的開台、下播事件，轉成 Discord 通知。"""

import logging

from sentry_bootstrap import capture_exception_safe
from starlib import sclient
from starlib.database import NotifyCommunityType
from starlib.messaging import Delivery, get_bus
from starlib.messaging.events.twitch_stream import TwitchStreamOfflineEvent, TwitchStreamOnlineEvent
from starlib.providers.social.models import TwitchStream

from ..extension import Cog_Extension
from .twitch_notify import DEFAULT_TWITCH_CHANNEL, ChannelMissing, NotConfigured, resolve_action_channel

log = logging.getLogger(__name__)


class TwitchLiveNotify(Cog_Extension):
    def __init__(self, bot):
        super().__init__(bot)
        # py-cord 沒有 cog_load；__init__ 在載入與 /reload 時都會執行，重複 subscribe 會取代舊 handler
        bus = get_bus()
        bus.subscribe(TwitchStreamOnlineEvent, self.on_stream_online, loop=bot.loop)
        bus.subscribe(TwitchStreamOfflineEvent, self.on_stream_offline, loop=bot.loop)

    def cog_unload(self) -> None:
        bus = get_bus()
        bus.unsubscribe(TwitchStreamOnlineEvent, self.on_stream_online)
        bus.unsubscribe(TwitchStreamOfflineEvent, self.on_stream_offline)

    async def on_stream_online(self, event: TwitchStreamOnlineEvent, delivery: Delivery) -> None:
        channel = resolve_action_channel(self.bot, event.broadcaster_id)
        if isinstance(channel, NotConfigured):
            return  # 沒設定通知頻道：整個不做，開台通知交給輪詢

        if not isinstance(channel, ChannelMissing):
            try:
                await channel.send(f"{event.broadcaster_name} 正在直播 {event.game_name}!")
            except Exception as e:
                log.warning("Twitch 開台通知發送失敗", extra={"twitch_id": event.broadcaster_id}, exc_info=e)
                capture_exception_safe(e, tags={"service": "discord", "source": "twitch_live_notify"})

        # 補送回來的同一事件視為已搶到（仍呼叫搶佔以寫入紀錄），寧可重複不要漏
        claimed = sclient.sqldb.claim_twitch_live(event.broadcaster_id, event.started_at)
        if claimed or delivery.redelivered:
            live = TwitchStream(
                id=event.stream_id,
                user_id=event.broadcaster_id,
                user_login=event.user_login,
                user_name=event.broadcaster_name,
                game_id=event.game_id,
                game_name=event.game_name,
                type=event.stream_type,
                title=event.title,
                viewer_count=event.viewer_count,
                started_at=event.started_at,
                language=event.language,
                thumbnail_url=event.thumbnail_url,
                tag_ids=event.tag_ids,
                tags=event.tags,
                is_mature=event.is_mature,
            )
            await self.bot.send_notify_communities(live.embed(event.profile_image_url), NotifyCommunityType.TwitchLive, event.broadcaster_id)

    async def on_stream_offline(self, event: TwitchStreamOfflineEvent, delivery: Delivery) -> None:
        channel = self.bot.get_channel(DEFAULT_TWITCH_CHANNEL)
        try:
            if channel:
                await channel.send(f"{event.broadcaster_name} ending stream.")
        finally:
            # 發送失敗也要清紀錄，否則下一次開台的通知要等紀錄被較新的開台時間覆蓋
            sclient.sqldb.clear_twitch_live(event.broadcaster_id, event.occurred_at)


def setup(bot):
    bot.add_cog(TwitchLiveNotify(bot))
