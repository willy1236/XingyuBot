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

class StardbCacheType(Enum):
    pass

class JsonCacheType(Enum):
    EarthquakeTimeFrom = "earthquake_timefrom"
    TwitchLive = "twitch"
    YoutubeVideo = "youtube"
    TwitchVideo = "twitch_v"
    TwitchClip = "twitch_c"
    WeatherWarning = "weather_warning"