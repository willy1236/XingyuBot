from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import discord

from ..database import sqldb
from ..dataExtractor import ApexInterface, OsuAPI, RiotAPI, SteamInterface
from ..fileDatabase import Jsondb
from ..models import PartialLOLPlayer
from ..settings import tz
from ..starAI import StarGeminiAI
from ..types import DBGame
from ..uiElement.view import ElectionPollView, PollView
from ..utilities import BotEmbed, ChoiceList, scheduler
from .cache import StarCache

if TYPE_CHECKING:
    from twitchAPI.twitch import Twitch

    from starDiscord import DiscordBot

class UserClient():
    """用戶查詢系統"""
    def get_user(self, user_id: str):
            """
            Retrieves a user from the database based on the provided user ID.

            Args:
                user_id (str): The ID of the user to retrieve.

            Returns:
                StarUser: The user object corresponding to the provided user ID.
            """
            return sqldb.get_user(user_id)
    
    def get_dcuser(self, discord_id: int, full=False, user_dc: discord.User = None):
        """
        Retrieves a Discord user from the database.

        Args:
            discord_id (int): The Discord ID of the user.
            full (bool, optional): Whether to retrieve the full user information. Defaults to False.
            user_dc (discord.User, optional): The Discord user object. Defaults to None.

        Returns:
            DiscordUser: The Discord user object from the database.
        """
        return sqldb.get_dcuser(discord_id, full, user_dc)

class GameClient():
    """遊戲查詢系統"""
    def get_user_game(self,discord_id,game:DBGame=None):
        """取得遊戲資料
        :param discord_id: 要查詢的用戶
        :param game: 提供將只查詢指定遊戲內容
        """
        dbdata = sqldb.get_game_data(discord_id,game)
        if not dbdata:
            return
        
        if game:
            game = DBGame(game)
            APIdata = None
            match game:
                case DBGame.STEAM:
                    APIdata = SteamInterface().get_user(dbdata['player_id'])
                case DBGame.OSU:
                    APIdata = OsuAPI().get_player(dbdata['player_name'])
                case DBGame.APEX:
                    APIdata = ApexInterface().get_player(dbdata['player_name'])
                case DBGame.LOL:
                    APIdata = RiotAPI().get_player_bypuuid(dbdata['other_id'])
                case _:
                    raise ValueError("Invalid game")
            return APIdata
        else:
            return dbdata
        
    def get_lol_player(self,riot_id=None,discord_id=None):
        """
        從資料庫取得資料，若沒有則從API取得
        :param riot_id: Riot ID（名稱#tag）
        :param discord_id: 若提供則先查詢資料庫
        """
        if discord_id:
            dbdata = sqldb.get_game_data(discord_id,"lol")
            if dbdata:
                player = PartialLOLPlayer(dbdata)
                if player.fullname == riot_id:
                    return player
        
        if riot_id:
            api = RiotAPI()
            user = api.get_riot_account_byname(riot_id)
            if user:
                player = api.get_player_bypuuid(user.puuid)
                return player if player else None

class BatClient():
    """TODO: 賭盤系統"""

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

        view = PollView(poll_id,sqldb,bot)
        return view
    
    def create_election_poll(self,title:str,options:list,creator_id:int,guild_id:int,bot:discord.bot=None):
        """創建選舉投票"""
        poll_id = sqldb.add_poll(title,creator_id,datetime.now(),None,guild_id,ban_alternate_account_voting=True,check_results_in_advance=False)
        sqldb.add_poll_option(poll_id,options)
        
        view = ElectionPollView(poll_id,sqldb,bot)
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
            
            position_name = ChoiceList.get_tw(pos_id,"position_option")
            embed.add_field(name=position_name, value=text, inline=False)
        
        return embed
    
class GiveawayClient():
    """TODO: 抽獎系統"""

class StarManager(
    GameClient,
    PointClient,
    PollClient,
    ElectionSystem,
):
    """整合各項系統的星羽資料管理物件
    :attr sqldb: Mysql Database
    :attr starai: AI
    :attr bot: Discord Bot
    :attr scheduler: Async Task Scheduler
    """
    def __init__(self):
        super().__init__()
        self.sqldb = sqldb
        self.scheduler = scheduler
        self.cache = StarCache() if self.sqldb else None

        self._starai:StarGeminiAI = None
        self.bot:DiscordBot = None
        self.twitch:Twitch = None
    
    @property
    def starai(self):
        if not self._starai:
            self._starai = StarGeminiAI()
        return self._starai