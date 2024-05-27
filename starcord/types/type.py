from enum import Enum, IntEnum

class NotifyCommunityType(IntEnum):
    TWITCH = 1
    YOUTUBE = 2
    TWITCH_VIDEO = 3
    TwitchClip = 4

class NotifyChannelType(IntEnum):
    Bot_Updates = 1
    EarthquakeNotifications = 2
    WeatherForecast = 3
    ApexRotation = 4
    AdminChannel = 5
    MemberJoin = 6
    MemberLeave = 7
    DynamicVoice = 8
    VoiceLog = 9

class CommunityType(Enum):
    Discord = 1