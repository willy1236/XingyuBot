import random,discord
from datetime import datetime
from .game import RiotClient,SteamInterface,OsuInterface,ApexInterface
from .mysql import MySQLDatabase
from starcord.models import *
from starcord.types import DBGame
from starcord.ui_element.view import PollView

class BatClient(MySQLDatabase):
    """賭盤系統"""

class GameClient(MySQLDatabase):
    """遊戲查詢系統"""
    def get_user_game(self,discord_id,game:DBGame=None):
        """取得遊戲資料
        :param discord_id: 要查詢的用戶
        :param game: 提供將只查詢指定遊戲內容
        """
        dbdata = self.get_game_data(discord_id,game)
        if not dbdata:
            return
        
        if game:
            game = DBGame(game)
            APIdata = None
            if game == DBGame.STEAM:
                APIdata = SteamInterface().get_user(dbdata['player_id'])
            elif game == DBGame.OSU:
                APIdata = OsuInterface().get_player(dbdata['player_name'])
            elif game == DBGame.APEX:
                APIdata = ApexInterface().get_player(dbdata['player_name'])
            elif game == DBGame.LOL:
                APIdata = RiotClient().get_player_bypuuid(dbdata['other_id'])
            return APIdata
        else:
            return dbdata
        
    def get_player_data(self,summoner_name=None,discord_id=None):
        """
        從資料庫取得資料，若沒有則從API取得
        :param summoner_name: 召喚師名稱
        :param discord_id: 若提供則先查詢資料庫
        """
        if discord_id:
            dbdata = self.get_game_data(discord_id,"lol")
            if dbdata:
                return PartialLOLPlayer(dbdata)
        
        if summoner_name:
            rclient = RiotClient()
            player = rclient.get_player_byname(summoner_name)
            return player

class PointClient(MySQLDatabase):
    """點數系統"""

    def daily_sign(self,discord_id):
        """每日簽到"""
        code = self.user_sign(discord_id)
        if code:
            return code
        scoin_add  = random.randint(5,10)
        rcoin_add = 0   # random.randint(3,5)
        self.sign_add_coin(discord_id,scoin_add,rcoin_add)
        return [scoin_add, rcoin_add]

class PollClient(MySQLDatabase):
    """投票系統"""
    def create_poll(self, title:str, options:list, creator_id:int, guild_id:int, alternate_account_can_vote=True,show_name=False,check_results_in_advance=True,results_only_initiator=False,only_role_list:list=[],role_magnification_dict:dict={}):
        poll_id = self.add_poll(title,creator_id,datetime.now(),None,guild_id,alternate_account_can_vote,show_name,check_results_in_advance,results_only_initiator)
        self.add_poll_option(poll_id,options)

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
            self.add_poll_role(poll_id,roleid,role_type,role_magnification)

        view = PollView(poll_id,self)
        return view

class GiveawayClient(MySQLDatabase):
    """todo:抽獎系統"""

class NoticeClient(MySQLDatabase):
    """
    ### 通知頻道系統
    由notice_dict進行緩存，使得讀取資料時可不用每次都讀取資料庫

    :attr notice_dict: 緩存各通知的頻道資料
    """
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.notice_dict = {}

    def get_notice_dict(self,channel_type:str=None) -> dict | list | None:
        """取得notice_dict資料"""
        return self.notice_dict.get(channel_type) if channel_type else self.notice_dict
    
    def set_notice_dict(self,channel_type,data):
        """設定notice_dict資料(dict)"""
        self.notice_dict[channel_type] = data
    
    def set_list_in_notice_dict(self,channel_type,new_data=None,remove_data=None):
        """更新notice_dict資料(list)"""
        dict_data = self.notice_dict[channel_type]
        if type(dict_data) != list:
            raise ValueError(f"{channel_type} expected list, got {type(dict_data)}.")
        
        if new_data:
            dict_data.append(new_data)
        if remove_data:
            dict_data.remove(remove_data)

    def init_NoticeClient(self,*channel_type):
        """
        從資料庫中提取資料\n
        :param channel_type: 若提供則只讀取指定資料
        """
        dict_type = ["dynamic_voice","voice_log"]
        list_type = ["twitch","dynamic_voice_room"]
        init_list = channel_type or dict_type + list_type
        
        for type in init_list:
            
            if type in dict_type:
                dbdata = self.get_notify_channel_by_type(type)
                dict = {}
                for data in dbdata:
                    guildid = data['guild_id']
                    channelid = data['channel_id']
                    roleid = data['role_id']
                    dict[guildid] = [channelid, roleid]
                #channel_dict[type] = dict
                self.set_notice_dict(type, dict)
            
            elif type in list_type:
                if type == "twitch":
                    dbdata = self.get_notify_community_userlist(type)
                    self.notice_dict[type] = dbdata
                elif type == "dynamic_voice_room":
                    dbdata = self.get_all_dynamic_voice()
                    self.notice_dict[type] = dbdata

    def getif_dynamic_voice_room(self,channel_id):
        """確認頻道是否為動態語音房"""
        return channel_id if channel_id in self.notice_dict['dynamic_voice_room'] else None

class StarClient(
    GameClient,
    PointClient,
    PollClient,
    NoticeClient,
):
    """整合各項系統的星羽客戶端"""
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)