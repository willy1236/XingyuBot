from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import discord
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from ..fileDatabase import Jsondb
from ..settings import tz

ytvideo_lives = {
    "live": "直播中",
    "upcoming": "即將直播",
    "none": "新影片"
    # 新影片或結束直播都是none
}

class TwitchUser(BaseModel):
    id: str
    login: str
    display_name: str
    type: str
    broadcaster_type: str
    description: str
    profile_image_url: str
    offline_image_url: str | None = None
    view_count: int
    email: str | None = None
    created_at: datetime
    url: str = None
        
    @model_validator(mode='after')
    def __post_init__(self):
        self.url = f"https://www.twitch.tv/{self.login}"
        self.created_at = self.created_at.astimezone(tz=tz)
        return self

    def desplay(self):
        embed = discord.Embed(
            title=self.display_name,
            url=self.url,
            description=self.description,
            color=0x6441a5,
            timestamp = self.created_at
            )
        embed.set_image(url=self.offline_image_url)
        embed.set_author(name=self.login,icon_url=self.profile_image_url)
        embed.add_field(name="觀看數",value=self.view_count)
        embed.add_field(name="頻道創建日期",value=self.created_at.strftime('%Y/%m/%d %H:%M:%S'))
        #embed.add_field(name="聯絡郵件",value=self.email)
        embed.set_footer(text=self.id)
        return embed

class TwitchStream(BaseModel):
    id: str
    user_id: str
    user_login: str
    user_name: str
    game_id: str
    game_name: str
    type: str
    title: str
    viewer_count: int
    started_at: datetime
    language: str
    thumbnail_url: str
    tag_ids: list[Optional[str]]
    tags: list[Optional[str]]
    is_mature: bool
    url: str = None
    live_thumbnail_url: str = None

    @model_validator(mode='after')
    def __post_init__(self):
        self.thumbnail_url = self.thumbnail_url.replace('{width}','960').replace('{height}','540')
        self.started_at = self.started_at.astimezone(tz=tz)
        self.url = f"https://www.twitch.tv/{self.user_login}"
        now = datetime.now(tz=tz)
        self.live_thumbnail_url = f"{self.thumbnail_url}?t={int(now.timestamp())}"
        return self

    def embed(self, profile_image_url:str=None):
        embed = discord.Embed(
            title=self.title,
            url=self.url,
            description=self.game_name,
            color=0x6441a5,
            timestamp = self.started_at,
            )
        embed.set_author(name=f"{self.user_name} 開台啦！", icon_url=profile_image_url or Jsondb.get_picture("twitch_001"))
        embed.set_image(url=self.live_thumbnail_url)
        embed.add_field(name="標籤", value=", ".join(self.tags))
        embed.set_footer(text=f"開始於")
        return embed

class TwitchVideo(BaseModel):
    id: str
    stream_id: Optional[str]
    user_id: str
    user_login: str
    user_name: str
    title: str
    description: str
    created_at: datetime
    published_at: datetime
    url: str
    thumbnail_url: str
    viewable: str
    view_count: int
    language: str
    type: str
    duration: str
    muted_segments: list[dict] | None = None
    
    @model_validator(mode='after')
    def __post_init__(self):
        self.created_at = self.created_at.astimezone(tz=tz)
        self.published_at = self.published_at.astimezone(tz=tz)
        self.thumbnail_url = self.thumbnail_url.replace('%{width}', '960').replace('%{height}', '540')
        return self

    def embed(self):
        embed = discord.Embed(
            title=self.title,
            url=self.url,
            description=self.description,
            color=0x6441a5,
            timestamp=self.created_at
            )
        embed.set_author(name=f"{self.user_name}", icon_url=Jsondb.get_picture("twitch_001"))
        embed.set_image(url=self.thumbnail_url)
        embed.set_footer(text=f"上傳時間")
        return embed

class TwitchClip(BaseModel):
    id: str
    url: str
    embed_url: str
    broadcaster_id: str
    broadcaster_name: str
    creator_id: str
    creator_name: str
    video_id: str
    game_id: str
    language: str
    title: str
    view_count: int
    created_at: datetime
    thumbnail_url: str
    duration: timedelta
    vod_offset: int | None = None
    is_featured: bool
    
    @model_validator(mode='after')
    def __post_init__(self):
        self.created_at = self.created_at.astimezone(tz=tz)
        self.thumbnail_url = self.thumbnail_url.replace('{width}', '960').replace('{height}', '540')
        return self

    def embed(self, original_video: TwitchVideo = None):
        embed = discord.Embed(
            title=self.title,
            url=self.url,
            color=0x6441a5,
            timestamp=self.created_at
            )
        embed.set_author(name=f"{self.broadcaster_name}", icon_url=Jsondb.get_picture("twitch_001"))
        embed.set_image(url=self.thumbnail_url)
        embed.add_field(name="剪輯者", value=self.creator_name)
        if original_video:
            embed.description = f"[{original_video.title}]({original_video.url})"
        embed.set_footer(text=f"上傳時間")
        return embed

class IdInfo(BaseModel):
    kind: str
    videoId: str

class YoutubeThumbnail(BaseModel):
    url: str
    width: int
    height: int

class YoutubeThumbnails(BaseModel):
    default: YoutubeThumbnail
    medium: YoutubeThumbnail
    high: YoutubeThumbnail

class Localized(BaseModel):
    title: str
    description: str
    
class ChannelSnippet(BaseModel):
    title: str
    description: str
    customUrl: str
    publishedAt: datetime
    thumbnails: YoutubeThumbnails
    localized: dict
    country: str | None = None

class ChannelStatistics(BaseModel):
    viewCount: int
    subscriberCount: int
    hiddenSubscriberCount: bool
    videoCount: int

class StreamSnippet(BaseModel):
    publishedAt: datetime
    channelId: str
    title: str
    description: str
    thumbnails: YoutubeThumbnails
    channelTitle: str
    liveBroadcastContent: str
    publishTime: datetime

class VideoSnippet(BaseModel):
    publishedAt: datetime
    channelId: str
    title: str
    description: str
    thumbnails: YoutubeThumbnails
    channelTitle: str
    tags: list[str | None] = Field(default_factory=list)
    categoryId: str
    liveBroadcastContent: str
    localized: Localized
    defaultAudioLanguage: str | None = None

class LiveStreamingDetails(BaseModel):
    actualStartTime: datetime | None = None
    actualEndTime: datetime | None = None
    scheduledStartTime: datetime = None
    scheduledEndTime: datetime | None = None
    concurrentViewers: int | None = None
    activeLiveChatId: str | None = None

class YoutubeChannel(BaseModel):
    kind: str
    etag: str
    id: str
    snippet: ChannelSnippet
    statistics: ChannelStatistics

    @model_validator(mode='after')
    def __post_init__(self):
        self.snippet.publishedAt = self.snippet.publishedAt.astimezone(tz=tz)
        return self

    def embed(self):
        embed = discord.Embed(
            title=self.snippet.title,
            url=f"https://www.youtube.com/channel/{self.id}",
            description=self.snippet.description,
            color=0xff0000,
            timestamp = self.snippet.publishedAt
            )
        embed.set_image(url=self.snippet.thumbnails.default.url)
        embed.add_field(name="頻道創建時間",value=self.snippet.publishedAt.strftime('%Y/%m/%d %H:%M:%S'))
        embed.add_field(name="訂閱數",value=f"{self.statistics.subscriberCount:,}")
        embed.add_field(name="影片數",value=f"{self.statistics.videoCount:,}")
        embed.add_field(name="觀看數",value=f"{self.statistics.viewCount:,}")
        embed.add_field(name="用戶代碼",value=self.snippet.customUrl)
        embed.set_footer(text=self.id)
        return embed

class YouTubeStream(BaseModel):
    kind: str
    etag: str
    id: IdInfo
    snippet: StreamSnippet

    @model_validator(mode='after')
    def __post_init__(self):
        self.snippet.publishedAt = self.snippet.publishedAt.astimezone(tz=tz)
        self.snippet.publishTime = self.snippet.publishTime.astimezone(tz=tz)
        return self

class YoutubeVideo(BaseModel):
    kind: str
    etag: str
    id: str
    snippet: VideoSnippet
    liveStreamingDetails: LiveStreamingDetails | None = None

    @model_validator(mode='after')
    def __post_init__(self):
        self.snippet.publishedAt = self.snippet.publishedAt.astimezone(tz=tz)
        if self.liveStreamingDetails:
            self.liveStreamingDetails.actualStartTime = self.liveStreamingDetails.actualStartTime.astimezone(tz=tz) if self.liveStreamingDetails.actualStartTime else None
            self.liveStreamingDetails.actualEndTime = self.liveStreamingDetails.actualEndTime.astimezone(tz=tz) if self.liveStreamingDetails.actualEndTime else None
            self.liveStreamingDetails.scheduledStartTime = self.liveStreamingDetails.scheduledStartTime.astimezone(tz=tz) if self.liveStreamingDetails.scheduledStartTime else None
            self.liveStreamingDetails.scheduledEndTime = self.liveStreamingDetails.scheduledEndTime.astimezone(tz=tz) if self.liveStreamingDetails.scheduledEndTime else None
        return self
    
    def embed(self):
        embed = discord.Embed(
            title=self.snippet.title,
            url=f"https://www.youtube.com/watch?v={self.id}",
            description=self.snippet.channelTitle,
            color=0xff0000,
            timestamp = self.snippet.publishedAt
            )

        if self.liveStreamingDetails:
            if self.liveStreamingDetails.actualEndTime and self.snippet.liveBroadcastContent == "none":
                embed.add_field(name="現況", value="直播結束")
            else:
                embed.add_field(name="現況", value=ytvideo_lives.get(self.snippet.liveBroadcastContent, "未知"))

            if self.liveStreamingDetails.scheduledStartTime and self.snippet.liveBroadcastContent == "upcoming":
                embed.add_field(name="預定直播時間", value=self.liveStreamingDetails.scheduledStartTime.strftime('%Y/%m/%d %H:%M:%S'))
            elif self.liveStreamingDetails.actualStartTime:
                embed.add_field(name="直播開始時間", value=self.liveStreamingDetails.actualStartTime.strftime('%Y/%m/%d %H:%M:%S'))
            if self.liveStreamingDetails.actualEndTime:
                embed.add_field(name="直播結束時間", value=self.liveStreamingDetails.actualEndTime.strftime('%Y/%m/%d %H:%M:%S'))
        else:
            embed.add_field(name="現況", value=ytvideo_lives.get(self.snippet.liveBroadcastContent, "未知"))
            embed.add_field(name="上傳時間",value=self.snippet.publishedAt.strftime('%Y/%m/%d %H:%M:%S'),inline=False)
            
        embed.set_image(url=self.snippet.thumbnails.high.url)
        return embed

class YoutubeRSSVideo(BaseModel):
    model_config = ConfigDict(extra='ignore')

    id: str
    link: HttpUrl
    yt_videoid: str
    yt_channelid: str
    title: str
    author_name: str = Field(alias='author')
    uplood_at: datetime = Field(alias='published')
    updated_at: datetime = Field(alias='updated')
    media_thumbnail: list[YoutubeThumbnail]
    
    @model_validator(mode='after')
    def __post_init__(self):
        self.uplood_at = self.uplood_at.astimezone(tz=tz)
        self.updated_at = self.updated_at.astimezone(tz=tz)
        return self

    def embed(self):
        embed = discord.Embed(
            title=self.title,
            url=self.link,
            description=self.author_name,
            color=0xff0000,
            timestamp = self.uplood_at
            )
        embed.add_field(name="上傳時間",value=self.uplood_at.strftime('%Y/%m/%d %H:%M:%S'),inline=False)
        #embed.add_field(name="更新時間",value=self.updated_at.strftime('%Y/%m/%d %H:%M:%S'),inline=True)
        embed.set_image(url=self.media_thumbnail[0].url)
        return embed
    
@dataclass
class YtSubscriptionDetails:
    callback_url: str
    state: str
    last_successful_verification: datetime
    expiration_time: datetime
    last_subscribe_request: datetime
    last_unsubscribe_request: datetime | None
    last_verification_error: datetime | None
    last_delivery_error: datetime | None
    last_item_delivered: datetime
    aggregate_statistics: str
    content_received: datetime | None
    content_delivered: datetime | None

    @property
    def has_verify(self):
        return self.state == "verified"