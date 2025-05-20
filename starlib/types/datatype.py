from enum import Enum, IntEnum

class NotifyCommunityType(IntEnum):
    TwitchLive = 1
    Youtube = 2
    TwitchVideo = 3
    TwitchClip = 4
    TwitterTweet = 5

class NotifyChannelType(IntEnum):
    AllAnnouncements = 1
    BotUpdates = 2
    MajorQuakeNotifications = 3
    WeatherForecast = 4
    ApexRotation = 5
    JoinLog = 6
    MemberJoin = 7
    MemberLeave = 8
    DynamicVoice = 9
    VoiceLog = 10
    WeatherWarning = 11
    SlightQuakeNotifications = 12
    LeaveLog = 13

class DBCacheType(Enum):
    DynamicVoice = "dynamic_voice"
    DynamicVoiceRoom = "dynamic_voice_room"
    VoiceLog = "voice_log"
    TwitchCmd = "twitch_cmd"

    @classmethod
    def from_notify_channel(cls, key: NotifyChannelType):
        return cache_dict.get(key)

cache_dict = {
    NotifyChannelType.DynamicVoice: DBCacheType.DynamicVoice,
    NotifyChannelType.VoiceLog: DBCacheType.VoiceLog,
}

class GameType(IntEnum):
    LOL = 1
    Apex = 2
    Osu = 3
    Steam = 4
    
class CommunityType(IntEnum):
    Discord = 1
    Twitch = 2
    Spotify = 3
    Youtube = 4
    Google = 4
    Twitter = 5

notify_to_community_map = {
    NotifyCommunityType.TwitchLive: CommunityType.Twitch,
    NotifyCommunityType.Youtube: CommunityType.Youtube,
    NotifyCommunityType.TwitchVideo: CommunityType.Twitch,
    NotifyCommunityType.TwitchClip: CommunityType.Twitch,
    NotifyCommunityType.TwitterTweet: CommunityType.Twitter,
}

class McssServerAction(IntEnum):
    Unknown = 0
    Stop = 1
    Start = 2
    Kill = 3
    Restart = 4

class McssServerStatues(IntEnum):
    Stopped = 0
    Running = 1
    Starting = 3
    Stopping = 4

    def __str__(self):
        return {
            0: "離線",
            1: "啟動",
            3: "啟動中",
            4: "停止中",
        }.get(self.value)
        
class APIType(IntEnum):
    Discord = 1
    CWA = 2
    Osu = 3
    TRN = 4
    Apex_Statue = 5
    Steam = 6
    Twitch = 7
    Google = 8
    Riot = 9
    Notion = 10
    Line = 11
    MCSS = 12
    Twitter = 13
    Rettiwt = 14
    DocAccount = 15