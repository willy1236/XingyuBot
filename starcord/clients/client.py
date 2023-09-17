import random
from starcord.database import sqldb
from starcord.models.model import GameInfoPage,GameInfo
from starcord.types import DBGame,Coins
from starcord.clients.game import *

class WarningClient:
    """警告系統"""

class BatClient:
    """賭盤系統"""

class GameClient:
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
            return GameInfoPage(dbdata)
        
    def set_game_data(self,discord_id:int,game:DBGame,player_name:str=None,player_id:str=None,account_id:str=None,other_id:str=None):
        """設定遊戲資料"""
        sqldb.set_game_data(discord_id,game,player_name,player_id,account_id,other_id)

    def remove_game_data(self,discord_id:int,game:DBGame):
        """移除遊戲資料"""
        sqldb.remove_game_data(discord_id,game)

class PointClient:
    """點數系統"""
    def get_scoin(self,discord_id):
        """取得用戶星幣數"""
        return sqldb.get_scoin(discord_id)
    
    def getif_scoin(self,discord_id,amount):
        """取得星幣足夠的用戶
        :return: 若足夠則回傳傳入的discord_id
        """
        return sqldb.getif_scoin(discord_id,amount)
    
    def transfer_scoin(self,giver_id:int,given_id:int,amount:int):
        """轉移星幣
        :param giver_id: 給予點數者
        :param given_id: 被給予點數者
        :param amount: 轉移的點數數量
        """
        return sqldb.transfer_scoin(giver_id,given_id,amount)
    
    def update_coins(self,discord_id:str,mod,coin_type:Coins,amount:int):
        """更改用戶的各項點數數量"""
        sqldb.update_coins(discord_id,mod,coin_type,amount)

    def daily_sign(self,discord_id):
        """每日簽到"""
        code = sqldb.user_sign(discord_id)
        if code:
            return code
        scoin_add  = random.randint(1,5)
        rcoin_add = 0   # random.randint(3,5)
        sqldb.sign_add_coin(discord_id,scoin_add,rcoin_add)
        return [scoin_add, rcoin_add]

class PollClient:
    """投票系統"""

class GiveawayClient:
    """todo:抽獎系統"""

class NoticeClient:
    """
    ### 通知頻道系統
    由notice_dict進行緩存，使得讀取資料時可不用每次都讀取資料庫

    :attr notice_dict: 緩存各通知的頻道資料
    """
    def __init__(self):
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
                dbdata = sqldb.get_notice_channel_by_type(type)
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
                    dbdata = sqldb.get_notice_community_userlist(type)
                    self.notice_dict[type] = dbdata
                elif type == "dynamic_voice_room":
                    dbdata = sqldb.get_all_dynamic_voice()
                    self.notice_dict[type] = dbdata

    def getif_dynamic_voice_room(self,channel_id):
        """確認頻道是否為動態語音房"""
        return channel_id if channel_id in self.notice_dict['dynamic_voice_room'] else None

class StarClient(
    NoticeClient,
    GameClient,
    PointClient
):
    """整合各項系統的星羽客戶端"""
    def __init__(self):
        super().__init__()