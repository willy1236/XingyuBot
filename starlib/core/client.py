from __future__ import annotations

import random
from datetime import datetime
from typing import TYPE_CHECKING

import discord

from ..database import sqldb
from ..fileDatabase import Jsondb
from ..settings import tz
from ..starAI import StarGeminiAI
from ..uiElement.view import PollView
from ..utilities import BotEmbed, scheduler
from ..base.base import BaseThread
from .cache import StardbCache

if TYPE_CHECKING:
    from twitchAPI.twitch import Twitch

    from starDiscord import DiscordBot

class PointClient():
    """點數系統"""

    def daily_sign(self,discord_id):
        """每日簽到"""
        code = sqldb.user_sign(discord_id)
        if code:
            return code
        scoin_add  = random.randint(5,10)
        rcoin_add = 0   # random.randint(3,5)
        sqldb.sign_add_coin(discord_id,scoin_add,rcoin_add)
        return [scoin_add, rcoin_add]

class PollClient():
    """投票系統"""
    def create_poll(self,
                    title:str,
                    options:list,
                    creator_id:int,
                    guild_id:int,
                    ban_alternate_account_voting=False,
                    show_name=False,
                    check_results_in_advance=True,
                    results_only_initiator=False,
                    number_of_user_votes=1,
                    only_role_list:list=[],
                    role_magnification_dict:dict={},
                    bot:discord.bot=None
                    ) -> PollView:
        """創建投票"""
        # TODO: add Poll config class
        poll_id = sqldb.add_poll(title,creator_id,datetime.now(tz=tz),None,guild_id,ban_alternate_account_voting,show_name,check_results_in_advance,results_only_initiator,number_of_user_votes)
        sqldb.add_poll_option(poll_id,options)

        poll_role_dict = {}
        for roleid in only_role_list:
            poll_role_dict[roleid] = [1,1]
            
        for roleid in role_magnification_dict:
            if roleid in poll_role_dict:
                poll_role_dict[roleid][1] = role_magnification_dict[roleid]
            else:
                poll_role_dict[roleid] = [2,role_magnification_dict[roleid]]

        for roleid in poll_role_dict:
            role_type = poll_role_dict[roleid][0]
            role_magnification = poll_role_dict[roleid][1]
            sqldb.add_poll_role(poll_id,roleid,role_type,role_magnification)

        poll = sqldb.get_poll(poll_id)
        view = PollView(poll,sqldb,bot)
        return view
    
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
            discord_id = data['discord_id']
            position = data['position']
            party_id = data['party_id']
            party_name = data['party_name']
            
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
            
            position_name = Jsondb.get_tw(pos_id,"position_option")
            embed.add_field(name=position_name, value=text, inline=False)
        
        return embed

class StarController(
    PointClient,
    PollClient,
    ElectionSystem,
):
    """整合各項系統的星羽資料管理物件 \\
    :attr sqldb: Mysql Database \\
    :attr starai: AI \\
    :attr bot: Discord Bot \\
    :attr scheduler: Async Task Scheduler
    """
    def __init__(self):
        super().__init__()
        self.sqldb = sqldb
        self.dbcache:StardbCache = StardbCache() if self.sqldb else None
        self.scheduler = scheduler

        self._starai:StarGeminiAI = None
        self.bot:DiscordBot = None
        self.twitch:Twitch = None

        self.twitch_bot_thread: BaseThread = None
        self.website_thread: BaseThread = None
        self.tunnel_thread: BaseThread = None
        self.twitchtunnel_thread: BaseThread = None
    
    @property
    def starai(self):
        if not self._starai:
            self._starai = StarGeminiAI()
        return self._starai