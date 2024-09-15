from typing import TypeVar
from ..database import sqldb
from ..types import NotifyCommunityType, NotifyChannelType
from ..utilities import log
from ..models.mysql import NotifyCommunity, NotifyChannel

T = TypeVar("T")

class StarCache:
    dict_type = [NotifyChannelType.DynamicVoice, NotifyChannelType.VoiceLog]
    list_type = ["dynamic_voice_room"]
    notify_community_type = [NotifyCommunityType.Twitch, NotifyCommunityType.Youtube, NotifyCommunityType.TwitchVideo, NotifyCommunityType.TwitchClip]

    def __init__(self):
        self.cache = {}
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
            pass

    def __getitem__(self, key):
        try:
            value: dict | list = self.cache[key]
            return value
        except KeyError:
            log.debug(f"cache KeyError: {key}")
            return None

    def update_dynamic_voice(self,add_channel=None,remove_channel=None):
        """更新動態語音頻道"""
        if add_channel and add_channel not in self.cache[NotifyChannelType.DynamicVoice]:
            self[NotifyChannelType.DynamicVoice].append(add_channel)
        if remove_channel:
            self[NotifyChannelType.DynamicVoice].remove(remove_channel)

    def update_dynamic_voice_room(self,add_channel=None,remove_channel=None):
        """更新動態語音房間"""
        if add_channel and add_channel not in self.cache["dynamic_voice_room"]:
            self["dynamic_voice_room"].append(add_channel)
        if remove_channel:
            self["dynamic_voice_room"].remove(remove_channel)

    def update_notify_channel(self,notify_type:NotifyChannelType):
        """更新通知頻道"""
        if notify_type not in self.dict_type:
            raise KeyError(f"Not implemented notify type: {notify_type}")
        dbdata = sqldb.get_notify_channel_by_type(notify_type)
        self[notify_type] = self.generate_notify_channel_dbdata(dbdata)

    def update_notify_community(self,notify_type:NotifyCommunityType=None):
        """更新社群通知"""
        if notify_type:
            if notify_type not in self.notify_community_type:
                raise KeyError(f"Not implemented notify type: {notify_type}")
            
            dbdata = sqldb.get_notify_community(notify_type)
            self[notify_type] = self.generate_notify_community_dbdata(dbdata)
        else:
            for t in self.notify_community_type:
                dbdata = sqldb.get_notify_community(t)
                self[t] = self.generate_notify_community_dbdata(dbdata)

    def getif_dynamic_voice_room(self,channel_id):
        """取得動態語音房間"""
        return channel_id if channel_id in self["dynamic_voice_room"] else None