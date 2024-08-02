from enum import IntEnum


class NotifyCommunityType(IntEnum):
    Twitch = 1
    Youtube = 2
    TwitchVideo = 3
    TwitchClip = 4

class NotifyChannelType(IntEnum):
    BotUpdates = 1
    EarthquakeNotifications = 2
    WeatherForecast = 3
    ApexRotation = 4
    AdminChannel = 5
    MemberJoin = 6
    MemberLeave = 7
    DynamicVoice = 8
    VoiceLog = 9

class CommunityType(IntEnum):
    Discord = 1
    Twitch = 2