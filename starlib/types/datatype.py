from enum import Enum, IntEnum


class NotifyCommunityType(IntEnum):
    TwitchLive = 1
    Youtube = 2
    TwitchVideo = 3
    TwitchClip = 4

class NotifyChannelType(IntEnum):
    AllAnnouncements = 1
    BotUpdates = 2
    MajorQuakeNotifications = 3
    WeatherForecast = 4
    ApexRotation = 5
    AdminChannel = 6
    MemberJoin = 7
    MemberLeave = 8
    DynamicVoice = 9
    VoiceLog = 10
    WeatherWarning = 11
    SlightQuakeNotifications = 12

class DBCacheType(Enum):
    Notify_channel = "notify_channel"
    Notify_community = "notify_community"

    @classmethod
    def map(cls, key: IntEnum):
        return cache_dict.get(key)

cache_dict = {
    NotifyChannelType: DBCacheType.Notify_channel,
    NotifyCommunityType: DBCacheType.Notify_community
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

notify_to_community_map = {
    NotifyCommunityType.TwitchLive: CommunityType.Twitch,
    NotifyCommunityType.Youtube: CommunityType.Youtube,
    NotifyCommunityType.TwitchVideo: CommunityType.Twitch,
    NotifyCommunityType.TwitchClip: CommunityType.Twitch,
}

class JsonCacheType(Enum):
    EarthquakeTimeFrom = "earthquake_timefrom"
    TwitchLive = "twitch"
    YoutubeVideo = "youtube"
    TwitchVideo = "twitch_v"
    TwitchClip = "twitch_c"
    WeatherWarning = "weather_warning"

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