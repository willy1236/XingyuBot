from enum import IntEnum, StrEnum


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
    # DynamicVoice = 9 # Deprecated, use DynamicVoiceLobby
    VoiceLog = 10
    WeatherWarning = 11
    SlightQuakeNotifications = 12
    LeaveLog = 13


class DBCacheType(StrEnum):
    DynamicVoiceLobby = "dynamic_voice"
    DynamicVoiceRoom = "dynamic_voice_room"
    VoiceLog = "voice_log"
    TwitchCmd = "twitch_cmd"
    VoiceTimeCounter = "voice_time_counter"

    @classmethod
    def from_notify_channel(cls, key: NotifyChannelType):
        return cache_dict.get(key)


cache_dict = {
    NotifyChannelType.VoiceLog: DBCacheType.VoiceLog,
}


class PlatformType(IntEnum):
    Discord = 1
    Twitch = 2


class GameType(IntEnum):
    LOL = 1
    Apex = 2
    Osu = 3
    Steam = 4
    Minecraft = 5


class CommunityType(IntEnum):
    Discord = 1
    Twitch = 2
    Spotify = 3
    Youtube = 4
    Google = 4
    Twitter = 5

    @classmethod
    def from_notify(cls, key: NotifyCommunityType):
        return notify_to_community_map.get(key)


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


mcss_server_statue_map = {0: "離線", 1: "啟動", 3: "啟動中", 4: "停止中"}


class McssServerStatues(IntEnum):
    Stopped = 0
    Running = 1
    Starting = 3
    Stopping = 4

    def __str__(self):
        return mcss_server_statue_map.get(self.value)


class APIType(IntEnum):
    Discord = 1
    CWA = 2
    Osu = 3
    TRN = 4
    ApexStatue = 5
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
    Tavily = 16
    ZeroTier = 17
    Virustotal = 18


class CredentialType(IntEnum):
    Id_Secret = 1
    Bearer_Token = 2
    Oauth2 = 3
    WebSub = 4
    LineBot = 5


class PrivilegeLevel(IntEnum):
    User = 0
    Level1 = 1
    Level2 = 2
    Level3 = 3


class YoutubeVideoStatue(IntEnum):
    Null = 0
    Live = 1
    Upcoming = 2


pet_tl = {"en": {"1": "shark", "2": "dog", "3": "cat", "4": "fox", "5": "wolf"}, "zh-tw": {"1": "鯊魚", "2": "狗", "3": "貓", "4": "狐狸", "5": "狼"}}


class PetType(IntEnum):
    SHARK = 1
    DOG = 2
    CAT = 3
    FOX = 4
    WOLF = 5

    def __str__(self):
        return self.text()

    def text(self, lcode="en"):
        return pet_tl[lcode][str(self.value)]


class Coins(IntEnum):
    Point = 1
    Stardust = 2
    Rcoin = 3


class Position(IntEnum):
    PRESIDENT = 1
    EXECUTIVE_PRESIDENT = 2
    LEGISLATIVE_PRESIDENT = 3
    JUDICIARY_PRESIDENT = 4


class WarningType(IntEnum):
    Warning = 1
    Timeout = 2
    Kick = 3
    Ban = 4
