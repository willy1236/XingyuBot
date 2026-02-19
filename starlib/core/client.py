from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from starlib.base import BaseThread
from starlib.database import sqldb
from starlib.fileDatabase import Jsondb
from starlib.settings import tz
from starlib.utils import BotEmbed, log

from .model import BaseEvent

if TYPE_CHECKING:
    from starDiscord import DiscordBot


class ElectionSystem():
    def election_format(self,session:int,bot:discord.Bot):
        dbdata = sqldb.get_election_full_by_session(session)
        guild = bot.get_guild(613747262291443742)

        # result = { "職位": { "用戶id": ["用戶提及", ["政黨"]]}}
        # init results
        results = {}
        for position in Jsondb.options["position_option"].keys():
            results[position] = {}

        # deal data
        for data in dbdata:
            discord_id = data["discord_id"]
            position = data["position"]
            party_id = data["party_id"]
            party_name = data["party_name"]

            if party_id:
                if guild:
                    role = guild.get_role(data["role_id"])
                    party = role.mention if role else party_name
                else:
                    party = party_name
            else:
                party = "無黨籍"
            user = bot.get_user(discord_id)
            username = user.mention if user else discord_id

            #新增資料
            if discord_id not in results[position]:
                results[position][discord_id] = [username, [party]]
            elif party not in results[position][discord_id][1]:
                results[position][discord_id][1].append(party)

        # create embed
        embed = BotEmbed.simple(f"第{session}屆中央選舉名單")
        for pos_id in results:
            text = ""
            count = 0
            for user_data in results[pos_id]:
                count += 1
                user_mention = results[pos_id][user_data][0]
                party_name = ",".join(results[pos_id][user_data][1])
                text += f"{count}. {user_mention} （{party_name}）\n"

            position_name = Jsondb.get_tw(pos_id, "position_option")
            embed.add_field(name=position_name, value=text, inline=False)

        return embed

class StarEventBus:
    """整合各項系統的星羽資料管理物件 \\
    :attr sqldb: Mysql Database \\
    :attr starai: AI \\
    :attr bot: Discord Bot \\
    """

    def __init__(self):
        # 資料結構改為：{ 事件型別: { 處理函式: 執行迴圈 } }
        self.listeners: dict[type[BaseEvent], dict[Callable, asyncio.AbstractEventLoop]] = {}

        self.sqldb = sqldb
        self.bot: DiscordBot | None = None
        self.scheduler: AsyncIOScheduler | None = None

        self.twitch_bot_thread: BaseThread | None = None
        self.website_thread: BaseThread | None = None
        self.tunnel_thread: BaseThread | None = None
        self.twitchtunnel_thread: BaseThread | None = None

    def subscribe(self, event_type: type[BaseEvent], handler: Callable, loop: asyncio.AbstractEventLoop = None) -> bool:
        """
        訂閱事件，若已註冊則忽略。
        :param event_type: 你想監聽的事件類別 (e.g., MCChatEvent)
        :return: True 表示註冊成功，False 表示已經註冊過。
        """
        if event_type not in self.listeners:
            self.listeners[event_type] = {}

        # 防呆機制：檢查該函式是否已經訂閱過此事件
        if handler in self.listeners[event_type]:
            log.warning(f"Handler {handler.__name__} already subscribed to {event_type.__name__}. Skipping.")
            return False

        try:
            current_loop = loop or asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        # 將 handler 作為 key，確保唯一性
        self.listeners[event_type][handler] = current_loop
        log.debug(f"Successfully registered handler {handler.__name__} to event type {event_type.__name__}")
        return True

    def unsubscribe(self, event_type: type[BaseEvent], handler: Callable) -> bool:
        """
        取消訂閱事件。
        :return: True 表示取消成功，False 表示找不到該註冊。
        """
        if event_type in self.listeners and handler in self.listeners[event_type]:
            del self.listeners[event_type][handler]
            log.debug(f"Successfully unsubscribed handler {handler.__name__} from event type {event_type.__name__}")

            # 順便清理空的字典，節省記憶體
            if not self.listeners[event_type]:
                del self.listeners[event_type]
            return True
        return False

    def publish(self, event: BaseEvent):
        """
        發布事件時，檢查所有訂閱者
        支援「多型訂閱」：如果你訂閱了 MinecraftEvent，也會收到 MCChatEvent
        """
        log.info(f"Publishing event: %s from %s", event.__class__.__name__, event.source, extra={"event": event.model_dump()})
        # 遍歷所有已註冊的事件類型（用 list 避免迭代中途字典被修改）
        for registered_type, handlers_dict in list(self.listeners.items()):
            # 關鍵：使用 isinstance 判斷 (多型)
            if isinstance(event, registered_type):
                for handler, target_loop in handlers_dict.items():
                    self._dispatch(handler, target_loop, event)

    def _dispatch(self, handler: Callable, loop: asyncio.AbstractEventLoop, event: BaseEvent):
        """處理執行緒與 Loop 切換的輔助函式"""
        event_name = event.__class__.__name__
        handler_name = handler.__name__

        def _on_done(future: asyncio.Future):
            if future.cancelled():
                return
            exc = future.exception()
            if exc:
                log.exception(
                    f"Error in handler {handler_name} for event {event_name}",
                    exc_info=exc,
                )

        try:
            if loop and loop.is_running():
                if asyncio.iscoroutinefunction(handler):
                    future = asyncio.run_coroutine_threadsafe(handler(event), loop)
                    future.add_done_callback(_on_done)
                else:
                    loop.call_soon_threadsafe(handler, event)
            else:
                # Fallback (通常不建議，除非確定在同個 thread)
                if asyncio.iscoroutinefunction(handler):
                    task = asyncio.create_task(handler(event))
                    task.add_done_callback(_on_done)
                else:
                    handler(event)
        except Exception:
            log.exception(f"Error dispatching event {event_name} to handler {handler_name}")
