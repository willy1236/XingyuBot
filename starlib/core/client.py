from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ..base.base import BaseThread
from ..database import sqldb
from ..fileDatabase import Jsondb
from ..settings import tz
from ..utils import BotEmbed

if TYPE_CHECKING:
    from twitchAPI.twitch import Twitch

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
        self.listeners: dict[str, list[Callable[..., Any]]] = {}

        self.sqldb = sqldb
        self.bot: DiscordBot | None = None
        self.twitch: Twitch | None = None
        self.scheduler: AsyncIOScheduler | None = None

        self.twitch_bot_thread: BaseThread | None = None
        self.website_thread: BaseThread | None = None
        self.tunnel_thread: BaseThread | None = None
        self.twitchtunnel_thread: BaseThread | None = None

    def subscribe(self, event_type: str, handler: Callable[..., Any]) -> None:
        self.listeners.setdefault(event_type, []).append(handler)

    def publish(self, event_type: str, **kwargs: object) -> None:
        for handler in self.listeners.get(event_type, []):
            # 這裡可以使用背景任務執行，避免卡住主執行緒
            handler(**kwargs)
