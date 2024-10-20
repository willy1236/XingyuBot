from typing import TYPE_CHECKING, Optional, overload

from ..database import sqldb
from ..models.mysql import NotifyChannel, NotifyCommunity
from ..types import NotifyChannelType, NotifyCommunityType
from ..utilities import log


class StardbCache:
    """
    處理資料庫的快取資料，用於通知頻道、社群通知等
    """
    dict_type = [NotifyChannelType.DynamicVoice, NotifyChannelType.VoiceLog]
    list_type = ["dynamic_voice_room"]
    # notify_community_type = [NotifyCommunityType.Twitch, NotifyCommunityType.Youtube, NotifyCommunityType.TwitchVideo, NotifyCommunityType.TwitchClip]
    
    if TYPE_CHECKING:
        cache: dict[
                str | NotifyChannelType | NotifyCommunityType,
                list[int] | dict[int, list[int | Optional[int]]] | list[str]
            ]
    
    def __init__(self):
        self.cache = dict()
        self.set_data()

    def set_data(self):
        """設定或重置所有資料"""
        for t in self.dict_type:
            self.update_notify_channel(t)

        for t in self.list_type:
            if t == "dynamic_voice_room":
                self[t] = sqldb.get_all_dynamic_voice()
    
        self.update_notify_community()

    @staticmethod
    def generate_notify_channel_dbdata(dbdata:list[NotifyChannel]):
        dict = {}
        for data in dbdata:
            guildid = data.guild_id
            channelid = data.channel_id
            roleid = data.role_id
            dict[guildid] = [channelid, roleid]
        return dict
    
    @staticmethod
    def generate_notify_community_dbdata(dbdata:list[NotifyCommunity]):
        lst = []
        for data in dbdata:
            if data.notify_name not in lst:
                lst.append(data.notify_name)
        return lst

    def __setitem__(self, key, value):
        self.cache[key] = value

    def __delitem__(self, key):
        try:
            del self.cache[key]
        except KeyError:
            log.warning(f"dbcache KeyError: {key}")
            pass

    @overload
    def __getitem__(self, key:str) -> list[int]:
        ...

    @overload
    def __getitem__(self, key:NotifyChannelType) -> dict[int, list[int | Optional[int]]]:
        ...

    @overload
    def __getitem__(self, key:NotifyCommunityType) -> list[str]:
        ...

    def __getitem__(self, key):
        try:
            value = self.cache[key]
            return value
        except KeyError:
            log.warning(f"dbcache KeyError: {key}")
            return None
        
    def __repr__(self):
        return str(self.cache)

    def update_dynamic_voice(self,add_channel=None,remove_channel=None):
        """更新動態語音頻道"""
        if add_channel and add_channel not in self.cache[NotifyChannelType.DynamicVoice]:
            self.cache[NotifyChannelType.DynamicVoice].append(add_channel)
        if remove_channel:
            self.cache[NotifyChannelType.DynamicVoice].remove(remove_channel)

    def update_dynamic_voice_room(self,add_channel=None,remove_channel=None):
        """更新動態語音房間"""
        if add_channel and add_channel not in self.cache["dynamic_voice_room"]:
            self.cache["dynamic_voice_room"].append(add_channel)
        if remove_channel:
            self.cache["dynamic_voice_room"].remove(remove_channel)

    def update_notify_channel(self,notify_type:NotifyChannelType):
        """更新通知頻道"""
        if notify_type not in self.dict_type:
            raise KeyError(f"Not implemented notify type: {notify_type}")
        dbdata = sqldb.get_notify_channel_by_type(notify_type)
        self.cache[notify_type] = self.generate_notify_channel_dbdata(dbdata)

    def update_notify_community(self,notify_type:NotifyCommunityType=None):
        """更新社群通知"""
        if notify_type:
            if notify_type not in NotifyCommunityType:
                raise KeyError(f"Not implemented notify type: {notify_type}")
            
            dbdata = sqldb.get_notify_community(notify_type)
            self.cache[notify_type] = self.generate_notify_community_dbdata(dbdata)
        else:
            for t in NotifyCommunityType:
                dbdata = sqldb.get_notify_community(t)
                self[t] = self.generate_notify_community_dbdata(dbdata)

    def getif_dynamic_voice_room(self,channel_id:int):
        """取得動態語音房間"""
        return channel_id if channel_id in self["dynamic_voice_room"] else None