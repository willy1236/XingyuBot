from starcord.database import sqldb

class WarningClient:
    """警告系統"""

class BatClient:
    """賭盤系統"""

class GameClient:
    """遊戲查詢系統"""

class NoticeClient:
    """
    通知頻道系統\n
    :attr notice_dict: 存放各通知的頻道資料
    """
    def __init__(self):
        self.notice_dict = {}

    def get_notice_dict(self,channel_type:str=None) -> dict | list | None:
        """取得notice_dict資料"""
        return self.notice_dict.get(channel_type) if channel_type else self.notice_dict
    
    def set_notice_dict(self,channel_type,data):
        """設定notice_dict資料(dict)"""
        self.notice_dict[channel_type] = data
    
    def set_lsit_in_notice_dict(self,channel_type,new_data=None,remove_data=None):
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
    NoticeClient
):
    """星羽客戶端"""
    def __init__(self):
        super().__init__()