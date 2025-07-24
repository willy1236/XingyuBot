import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TypeVar

import discord
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, computed_field, field_validator, model_validator

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

    @model_validator(mode="after")
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
            timestamp=self.created_at
        )
        embed.set_image(url=self.offline_image_url)
        embed.set_author(name=self.login, icon_url=self.profile_image_url)
        embed.add_field(name="觀看數", value=self.view_count)
        embed.add_field(name="頻道創建日期", value=self.created_at.strftime("%Y/%m/%d %H:%M:%S"))
        # embed.add_field(name="聯絡郵件",value=self.email)
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
    tag_ids: list[str | None]
    tags: list[str | None]
    is_mature: bool
    url: str = None
    live_thumbnail_url: str = None

    @model_validator(mode="after")
    def __post_init__(self):
        self.thumbnail_url = self.thumbnail_url.replace("{width}", "960").replace("{height}", "540")
        self.started_at = self.started_at.astimezone(tz=tz)
        self.url = f"https://www.twitch.tv/{self.user_login}"
        now = datetime.now(tz=tz)
        self.live_thumbnail_url = f"{self.thumbnail_url}?t={int(now.timestamp())}"
        return self

    def embed(self, profile_image_url: str = None):
        embed = discord.Embed(
            title=self.title,
            url=self.url,
            description=self.game_name,
            color=0x6441a5,
            timestamp=self.started_at,
        )
        embed.set_author(name=f"{self.user_name} 開台啦！",
                         icon_url=profile_image_url or Jsondb.get_picture("twitch_001"))
        embed.set_image(url=self.live_thumbnail_url)
        embed.add_field(name="標籤", value=", ".join(self.tags))
        embed.set_footer(text="開始於")
        return embed


class TwitchVideo(BaseModel):
    id: str
    stream_id: str | None
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

    @model_validator(mode="after")
    def __post_init__(self):
        self.created_at = self.created_at.astimezone(tz=tz)
        self.published_at = self.published_at.astimezone(tz=tz)
        self.thumbnail_url = self.thumbnail_url.replace("%{width}", "960").replace("%{height}", "540")
        return self

    def embed(self):
        embed = discord.Embed(
            title=self.title,
            url=self.url,
            description=self.description,
            color=0x6441a5,
            timestamp=self.created_at
        )
        embed.set_author(name=f"{self.user_name}",
                         icon_url=Jsondb.get_picture("twitch_001"))
        embed.set_image(url=self.thumbnail_url)
        embed.set_footer(text="上傳時間")
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

    @model_validator(mode="after")
    def __post_init__(self):
        self.created_at = self.created_at.astimezone(tz=tz)
        self.thumbnail_url = self.thumbnail_url.replace("{width}", "960").replace("{height}", "540")
        return self

    def embed(self, original_video: TwitchVideo = None):
        embed = discord.Embed(
            title=self.title,
            url=self.url,
            color=0x6441a5,
            timestamp=self.created_at
        )
        embed.set_author(name=f"{self.broadcaster_name}",
                         icon_url=Jsondb.get_picture("twitch_001"))
        embed.set_image(url=self.thumbnail_url)
        embed.add_field(name="剪輯者", value=self.creator_name)
        if original_video:
            embed.description = f"[{original_video.title}]({original_video.url})"
        embed.set_footer(text="上傳時間")
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
    scheduledStartTime: datetime | None = None
    scheduledEndTime: datetime | None = None
    concurrentViewers: int | None = None
    activeLiveChatId: str | None = None


class YoutubeChannel(BaseModel):
    kind: str
    etag: str
    id: str
    snippet: ChannelSnippet
    statistics: ChannelStatistics

    @model_validator(mode="after")
    def __post_init__(self):
        self.snippet.publishedAt = self.snippet.publishedAt.astimezone(tz=tz)
        return self

    def embed(self):
        embed = discord.Embed(
            title=self.snippet.title,
            url=f"https://www.youtube.com/channel/{self.id}",
            description=self.snippet.description,
            color=0xff0000,
            timestamp=self.snippet.publishedAt
        )
        embed.set_image(url=self.snippet.thumbnails.default.url)
        embed.add_field(name="頻道創建時間", value=self.snippet.publishedAt.strftime("%Y/%m/%d %H:%M:%S"))
        embed.add_field(
            name="訂閱數", value=f"{self.statistics.subscriberCount:,}")
        embed.add_field(name="影片數", value=f"{self.statistics.videoCount:,}")
        embed.add_field(name="觀看數", value=f"{self.statistics.viewCount:,}")
        embed.add_field(name="用戶代碼", value=self.snippet.customUrl)
        embed.set_footer(text=self.id)
        return embed


class YouTubeStream(BaseModel):
    kind: str
    etag: str
    id: IdInfo
    snippet: StreamSnippet

    @model_validator(mode="after")
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

    @model_validator(mode="after")
    def __post_init__(self):
        self.snippet.publishedAt = self.snippet.publishedAt.astimezone(tz=tz)
        if self.liveStreamingDetails:
            self.liveStreamingDetails.actualStartTime = (
                self.liveStreamingDetails.actualStartTime.astimezone(tz=tz) if self.liveStreamingDetails.actualStartTime else None
            )
            self.liveStreamingDetails.actualEndTime = (
                self.liveStreamingDetails.actualEndTime.astimezone(tz=tz) if self.liveStreamingDetails.actualEndTime else None
            )
            self.liveStreamingDetails.scheduledStartTime = (
                self.liveStreamingDetails.scheduledStartTime.astimezone(tz=tz) if self.liveStreamingDetails.scheduledStartTime else None
            )
            self.liveStreamingDetails.scheduledEndTime = (
                self.liveStreamingDetails.scheduledEndTime.astimezone(tz=tz) if self.liveStreamingDetails.scheduledEndTime else None
            )
        return self

    def embed(self):
        embed = discord.Embed(
            title=self.snippet.title,
            url=f"https://www.youtube.com/watch?v={self.id}",
            description=self.snippet.channelTitle,
            color=0xFF0000,
            timestamp=self.snippet.publishedAt,
        )

        if self.liveStreamingDetails:
            if self.liveStreamingDetails.actualEndTime and self.snippet.liveBroadcastContent == "none":
                embed.add_field(name="現況", value="直播結束")
            else:
                embed.add_field(name="現況", value=ytvideo_lives.get(self.snippet.liveBroadcastContent, "未知"))

            if self.liveStreamingDetails.scheduledStartTime and self.snippet.liveBroadcastContent == "upcoming":
                embed.add_field(name="預定直播時間", value=self.liveStreamingDetails.scheduledStartTime.strftime("%Y/%m/%d %H:%M:%S"))
            elif self.liveStreamingDetails.actualStartTime:
                embed.add_field(name="直播開始時間", value=self.liveStreamingDetails.actualStartTime.strftime("%Y/%m/%d %H:%M:%S"))
            if self.liveStreamingDetails.actualEndTime:
                embed.add_field(name="直播結束時間", value=self.liveStreamingDetails.actualEndTime.strftime("%Y/%m/%d %H:%M:%S"))
        else:
            embed.add_field(name="現況", value=ytvideo_lives.get(self.snippet.liveBroadcastContent, "未知"))
            embed.add_field(name="上傳時間", value=self.snippet.publishedAt.strftime("%Y/%m/%d %H:%M:%S"))

        embed.set_image(url=self.snippet.thumbnails.high.url)
        return embed

    @property
    def is_live_end(self) -> bool:
        return bool(self.liveStreamingDetails and self.liveStreamingDetails.actualEndTime)

    @property
    def is_live_upcoming(self) -> bool:
        return self.snippet.liveBroadcastContent == "upcoming"

    @property
    def is_live_upcoming_with_time(self) -> bool:
        return bool(self.liveStreamingDetails is not None and self.liveStreamingDetails.scheduledStartTime and not self.liveStreamingDetails.actualEndTime)

    @property
    def is_live_getting_startrd(self) -> bool:
        now = datetime.now(tz=tz)
        return bool(
            self.liveStreamingDetails
            and self.liveStreamingDetails.actualStartTime
            and not self.liveStreamingDetails.actualEndTime
            and (now - self.liveStreamingDetails.actualStartTime) < timedelta(minutes=1)
        )


class YoutubeRSSVideo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    link: HttpUrl
    yt_videoid: str
    yt_channelid: str
    title: str
    author_name: str = Field(alias="author")
    uplood_at: datetime = Field(alias="published")
    updated_at: datetime = Field(alias="updated")
    media_thumbnail: list[YoutubeThumbnail]

    @model_validator(mode="after")
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
            timestamp=self.uplood_at
        )
        embed.add_field(name="上傳時間", value=self.uplood_at.strftime("%Y/%m/%d %H:%M:%S"), inline=False)
        # embed.add_field(name="更新時間",value=self.updated_at.strftime('%Y/%m/%d %H:%M:%S'),inline=True)
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


class RssHubTwitterTweet(BaseModel):
    title: str
    title_detail: dict
    summary: str
    summary_detail: dict
    links: list[dict]
    link: str
    id: str
    guidislink: bool
    published: str
    published_parsed: datetime  # 特殊處理
    authors: list[dict]
    author: str
    author_detail: dict

    @field_validator("published_parsed", mode="before")
    @classmethod
    def parse_published_parsed(cls, v):
        if isinstance(v, datetime):
            return v
        if isinstance(v, time.struct_time):
            # struct_time 轉成 datetime
            return datetime(*v[:6], tzinfo=timezone.utc).astimezone(tz=tz)
        if isinstance(v, dict):
            # 假如來的是 dict（像 JSON 會這樣），先轉成 tuple 再轉 datetime
            return datetime(*tuple(v.values())[:6])
        raise ValueError(f"Unsupported type for published_parsed: {type(v)}")

    @computed_field
    @property
    def is_retweet(self) -> bool:
        return self.title.startswith("RT ")


DATETIME_FORMAT = "%a %b %d %H:%M:%S %z %Y"  # Twitter 時間格式


class RettiwtTweetUser(BaseModel):
    id: str
    userName: str
    fullName: str
    createdAt: datetime
    description: str
    isVerified: bool
    likeCount: int
    followersCount: int
    followingsCount: int
    statusesCount: int
    pinnedTweet: str | None
    profileBanner: HttpUrl | None
    profileImage: HttpUrl | None

    @field_validator("createdAt", mode="before")
    @classmethod
    def parse_created_at(cls, v: str) -> datetime:
        return datetime.strptime(v, DATETIME_FORMAT)


class RettiwtTweetEntity(BaseModel):
    hashtags: list[str | None] = Field(default_factory=list)
    mentionedUsers: list[str | None] = Field(default_factory=list)
    urls: list[str | None] = Field(default_factory=list)


class RettiwtTweetMedia(BaseModel):
    url: HttpUrl
    type: str


class RettiwtTweetItem(BaseModel):
    id: str
    createdAt: datetime
    tweetBy: RettiwtTweetUser
    entities: RettiwtTweetEntity
    media: list[RettiwtTweetMedia | None] = Field(default_factory=list)
    fullText: str
    lang: str
    quoteCount: int
    replyCount: int
    retweetCount: int
    likeCount: int
    viewCount: int
    bookmarkCount: int

    @field_validator("createdAt", mode="before")
    @classmethod
    def parse_created_at(cls, v: str) -> datetime:
        return datetime.strptime(v, DATETIME_FORMAT).astimezone(tz=tz)

    @property
    def url(self) -> str:
        return f"https://twitter.com/{self.tweetBy.userName}/status/{self.id}"

    @property
    def is_retweet(self) -> bool:
        return self.fullText.startswith("RT @")


class RettiwtTweetTimeLineResponse(BaseModel):
    list: list[RettiwtTweetItem]
    next: dict | None = None


# Notion API Models
class NotionUser(BaseModel):
    object: str
    id: str
    type: str | None = None  # 設為可選字段
    name: str | None = None
    avatar_url: str | None = None
    person: dict | None = None
    bot: dict | None = None


class NotionParent(BaseModel):
    type: str
    database_id: str | None = None
    page_id: str | None = None
    workspace: bool | None = None
    block_id: str | None = None


class NotionRichTextContent(BaseModel):
    content: str | None = None
    link: str | None = None


class NotionRichTextAnnotations(BaseModel):
    bold: bool
    italic: bool
    strikethrough: bool
    underline: bool
    code: bool
    color: str = "default"


class NotionRichText(BaseModel):
    type: str
    text: NotionRichTextContent | None = None
    mention: dict | None = None
    equation: dict | None = None
    annotations: NotionRichTextAnnotations | None = None
    plain_text: str
    href: str | None = None
    link: str | None = None


class NotionPropertyValue(BaseModel):
    id: str
    type: str
    # Title property
    title: list[NotionRichText] | None = None
    # Rich text property
    rich_text: list[NotionRichText] | None = None
    # Number property
    number: float | int | None = None
    # Select property
    select: dict | None = None
    # Multi-select property
    multi_select: list[dict] | None = None
    # Date property
    date: dict | None = None
    # People property
    people: list[NotionUser] | None = None
    # Files property
    files: list[dict] | None = None
    # Checkbox property
    checkbox: bool | None = None
    # URL property
    url: str | None = None
    # Email property
    email: str | None = None
    # Phone number property
    phone_number: str | None = None
    # Formula property
    formula: dict | None = None
    # Relation property
    relation: list[dict] | None = None
    # Rollup property
    rollup: dict | None = None
    # Created time property
    created_time: datetime | None = None
    # Created by property
    created_by: NotionUser | None = None
    # Last edited time property
    last_edited_time: datetime | None = None
    # Last edited by property
    last_edited_by: NotionUser | None = None
    # Status property
    status: dict | None = None
    # Unique ID property
    unique_id: dict | None = None
    # Verification property
    verification: dict | None = None

    @field_validator("created_time", "last_edited_time", mode="before")
    @classmethod
    def parse_datetime(cls, v):
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(tz=tz)
        return v


class NotionIcon(BaseModel):
    type: str
    emoji: str | None = None
    external: dict | None = None
    file: dict | None = None


class NotionCover(BaseModel):
    type: str
    external: dict | None = None
    file: dict | None = None


class NotionPage(BaseModel):
    object: str
    id: str
    created_time: datetime
    created_by: NotionUser
    last_edited_time: datetime
    last_edited_by: NotionUser
    cover: NotionCover | None = None
    icon: NotionIcon | None = None
    parent: NotionParent
    archived: bool
    properties: dict[str, NotionPropertyValue]
    url: str
    public_url: str | None = None

    @field_validator("created_time", "last_edited_time", mode="before")
    @classmethod
    def parse_datetime(cls, v):
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(tz=tz)
        return v

    def get_plain_text(self):
        """從頁面屬性中提取純文本"""
        for prop_value in self.properties.values():
            if prop_value.type == "title" and prop_value.title:
                return prop_value.title[0].plain_text if prop_value.title else ""

    def embed(self):
        title = "未命名頁面"
        # 尋找 title 屬性
        for prop_name, prop_value in self.properties.items():
            if prop_value.type == "title" and prop_value.title:
                title = prop_value.title[0].plain_text if prop_value.title else "未命名頁面"
                break

        embed = discord.Embed(title=title, url=self.url, color=0x2F3437, timestamp=self.last_edited_time)
        embed.set_author(name="Notion 頁面", icon_url="https://www.notion.so/images/favicon.ico")
        embed.add_field(name="建立時間", value=self.created_time.strftime("%Y/%m/%d %H:%M:%S"))
        embed.add_field(name="最後編輯", value=self.last_edited_time.strftime("%Y/%m/%d %H:%M:%S"))
        embed.add_field(name="建立者", value=self.created_by.name or "未知")
        embed.add_field(name="最後編輯者", value=self.last_edited_by.name or "未知")

        # 添加圖示資訊
        if self.icon:
            if self.icon.type == "emoji":
                embed.add_field(name="圖示", value=self.icon.emoji or "無")
            elif self.icon.type in ["external", "file"]:
                embed.add_field(name="圖示", value="圖片")

        embed.set_footer(text=f"頁面 ID: {self.id}")
        return embed


class NotionDatabase(BaseModel):
    object: str
    id: str
    created_time: datetime
    created_by: NotionUser
    last_edited_time: datetime
    last_edited_by: NotionUser
    title: list[NotionRichText] | None = None  # 可選字段
    description: list[NotionRichText] = Field(default_factory=list)
    icon: NotionIcon | None = None
    cover: NotionCover | None = None
    properties: dict[str, dict]
    parent: NotionParent
    url: str
    archived: bool
    is_inline: bool | None = None  # 可選字段
    public_url: str | None = None

    @field_validator("created_time", "last_edited_time", mode="before")
    @classmethod
    def parse_datetime(cls, v):
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(tz=tz)
        return v

    def embed(self):
        title = "未命名資料庫"
        if self.title:
            title = self.title[0].plain_text if self.title else "未命名資料庫"

        description = "無描述"
        if self.description:
            description = self.description[0].plain_text if self.description else "無描述"

        embed = discord.Embed(title=title, url=self.url, description=description, color=0x2F3437, timestamp=self.last_edited_time)
        embed.set_author(name="Notion 資料庫", icon_url="https://www.notion.so/images/favicon.ico")
        embed.add_field(name="建立時間", value=self.created_time.strftime("%Y/%m/%d %H:%M:%S"))
        embed.add_field(name="最後編輯", value=self.last_edited_time.strftime("%Y/%m/%d %H:%M:%S"))
        embed.add_field(name="屬性數量", value=len(self.properties))
        embed.add_field(name="建立者", value=self.created_by.name or "未知")
        embed.add_field(name="最後編輯者", value=self.last_edited_by.name or "未知")
        embed.set_footer(text=f"資料庫 ID: {self.id}")
        return embed


class NotionParagraph(BaseModel):
    rich_text: list[NotionRichText] = Field(default_factory=list)
    color: str = "default"
    children: list[dict] = Field(default_factory=list)


class NotionHeading(BaseModel):
    rich_text: list[NotionRichText] = Field(default_factory=list)
    color: str = "default"
    is_toggleable: bool = False
    children: list[dict] = Field(default_factory=list)


class NotionBulletedListItem(BaseModel):
    rich_text: list[NotionRichText] = Field(default_factory=list)
    color: str = "default"
    children: list[dict] = Field(default_factory=list)


class NotionNumberedListItem(BaseModel):
    rich_text: list[NotionRichText] = Field(default_factory=list)
    color: str = "default"
    children: list[dict] = Field(default_factory=list)


class NotionToDo(BaseModel):
    rich_text: list[NotionRichText] = Field(default_factory=list)
    checked: bool = False
    color: str = "default"
    children: list[dict] = Field(default_factory=list)


class NotionToggle(BaseModel):
    rich_text: list[NotionRichText] = Field(default_factory=list)
    color: str = "default"
    children: list[dict] = Field(default_factory=list)


class NotionCode(BaseModel):
    rich_text: list[NotionRichText] = Field(default_factory=list)
    language: str = "plain text"
    caption: list[NotionRichText] = Field(default_factory=list)


class NotionCallout(BaseModel):
    rich_text: list[NotionRichText] = Field(default_factory=list)
    icon: NotionIcon | None = None
    color: str = "default"
    children: list[dict] = Field(default_factory=list)


class NotionQuote(BaseModel):
    rich_text: list[NotionRichText] = Field(default_factory=list)
    color: str = "default"
    children: list[dict] = Field(default_factory=list)


class NotionBlock(BaseModel):
    object: str
    id: str
    parent: NotionParent
    created_time: datetime
    created_by: NotionUser
    last_edited_time: datetime
    last_edited_by: NotionUser
    archived: bool
    has_children: bool
    type: str
    paragraph: NotionParagraph | None = None
    heading_1: NotionHeading | None = None
    heading_2: NotionHeading | None = None
    heading_3: NotionHeading | None = None
    bulleted_list_item: NotionBulletedListItem | None = None
    numbered_list_item: NotionNumberedListItem | None = None
    quote: NotionQuote | None = None
    to_do: NotionToDo | None = None
    toggle: NotionToggle | None = None
    template: dict | None = None
    synced_block: dict | None = None
    child_page: dict | None = None
    child_database: dict | None = None
    equation: dict | None = None
    code: NotionCode | None = None
    callout: NotionCallout | None = None
    divider: dict | None = None
    breadcrumb: dict | None = None
    table_of_contents: dict | None = None
    column_list: dict | None = None
    column: dict | None = None
    link_preview: dict | None = None
    template_mention: dict | None = None
    link_to_page: dict | None = None
    table: dict | None = None
    table_row: dict | None = None
    embed: dict | None = None
    bookmark: dict | None = None
    image: dict | None = None
    video: dict | None = None
    pdf: dict | None = None
    file: dict | None = None
    audio: dict | None = None
    unsupported: dict | None = None

    @field_validator("created_time", "last_edited_time", mode="before")
    @classmethod
    def parse_datetime(cls, v):
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(tz=tz)
        return v

    def get_plain_text(self) -> str:
        """獲取區塊的純文本內容"""
        if self.type == "paragraph" and self.paragraph:
            return "".join([rt.plain_text for rt in self.paragraph.rich_text])
        elif self.type in ["heading_1", "heading_2", "heading_3"]:
            heading: NotionHeading = getattr(self, self.type)
            if heading:
                return "".join([rt.plain_text for rt in heading.rich_text])
        elif self.type == "bulleted_list_item" and self.bulleted_list_item:
            return "".join([rt.plain_text for rt in self.bulleted_list_item.rich_text])
        elif self.type == "numbered_list_item" and self.numbered_list_item:
            return "".join([rt.plain_text for rt in self.numbered_list_item.rich_text])
        elif self.type == "to_do" and self.to_do:
            return "".join([rt.plain_text for rt in self.to_do.rich_text])
        elif self.type == "toggle" and self.toggle:
            return "".join([rt.plain_text for rt in self.toggle.rich_text])
        elif self.type == "quote" and self.quote:
            return "".join([rt.plain_text for rt in self.quote.rich_text])
        elif self.type == "code" and self.code:
            return "".join([rt.plain_text for rt in self.code.rich_text])
        elif self.type == "callout" and self.callout:
            return "".join([rt.plain_text for rt in self.callout.rich_text])
        else:
            return ""

    def embed_dc(self):
        """為區塊建立 Discord embed"""
        plain_text = self.get_plain_text()

        # 根據區塊類型設定不同的顏色和標題
        color_map = {
            "paragraph": 0x2F3437,
            "heading_1": 0x0080FF,
            "heading_2": 0x4169E1,
            "heading_3": 0x6495ED,
            "bulleted_list_item": 0x32CD32,
            "numbered_list_item": 0x32CD32,
            "to_do": 0xFFD700,
            "toggle": 0x9370DB,
            "quote": 0x708090,
            "code": 0x2F4F4F,
            "callout": 0xFF6347,
        }

        type_names = {
            "paragraph": "段落",
            "heading_1": "標題 1",
            "heading_2": "標題 2",
            "heading_3": "標題 3",
            "bulleted_list_item": "項目符號",
            "numbered_list_item": "編號清單",
            "to_do": "待辦事項",
            "toggle": "摺疊",
            "quote": "引用",
            "code": "程式碼",
            "callout": "標注",
        }

        embed = discord.Embed(
            title=f"{type_names.get(self.type, self.type)}",
            description=plain_text[:2000] if plain_text else "無內容",
            color=color_map.get(self.type, 0x2F3437),
            timestamp=self.last_edited_time,
        )

        embed.set_author(name="Notion 區塊", icon_url="https://www.notion.so/images/favicon.ico")
        embed.add_field(name="建立時間", value=self.created_time.strftime("%Y/%m/%d %H:%M:%S"))
        embed.add_field(name="最後編輯", value=self.last_edited_time.strftime("%Y/%m/%d %H:%M:%S"))
        embed.add_field(name="有子區塊", value="是" if self.has_children else "否")

        # 特殊處理某些區塊類型
        if self.type == "to_do" and self.to_do:
            embed.add_field(name="已完成", value="是" if self.to_do.checked else "否")
        elif self.type == "code" and self.code:
            embed.add_field(name="語言", value=self.code.language)

        embed.set_footer(text=f"區塊 ID: {self.id}")
        return embed


class NotionQueryResponse(BaseModel):
    object: str
    results: list[NotionPage | NotionDatabase | NotionBlock]
    next_cursor: str | None = None
    has_more: bool
    type: str | None = None
    page_or_database: dict | None = None

    @field_validator("results", mode="before")
    @classmethod
    def parse_results(cls, v):
        parsed_results = []
        for item in v:
            try:
                if item.get("object") == "page":
                    parsed_results.append(NotionPage(**item))
                elif item.get("object") == "database":
                    parsed_results.append(NotionDatabase(**item))
                elif item.get("object") == "block":
                    parsed_results.append(NotionBlock(**item))
                else:
                    raise ValueError(f"未知的 Notion 物件類型: {item.get('object')}")
            except Exception as e:
                print(f"解析項目時發生錯誤: {e}")
                print(f"項目數據: {item}")
        return parsed_results
