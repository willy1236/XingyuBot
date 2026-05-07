import time
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, computed_field, field_validator, model_validator

from v2_starlib.base import UTCDateTime
from v2_starlib.utils.time import convert_tz, nowtz

ytvideo_lives = {
    "live": "直播中",
    "upcoming": "即將直播",
    "none": "新影片",
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
    created_at: UTCDateTime
    url: str = None

    @model_validator(mode="after")
    def __post_init__(self):
        self.url = f"https://www.twitch.tv/{self.login}"
        return self


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
    started_at: UTCDateTime
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
        self.url = f"https://www.twitch.tv/{self.user_login}"
        self.live_thumbnail_url = f"{self.thumbnail_url}?t={int(nowtz().timestamp())}"
        return self


class TwitchVideo(BaseModel):
    id: str
    stream_id: str | None
    user_id: str
    user_login: str
    user_name: str
    title: str
    description: str
    created_at: UTCDateTime
    published_at: UTCDateTime
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
        self.thumbnail_url = self.thumbnail_url.replace("%{width}", "960").replace("%{height}", "540")
        return self


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
    created_at: UTCDateTime
    thumbnail_url: str
    duration: timedelta
    vod_offset: int | None = None
    is_featured: bool

    @model_validator(mode="after")
    def __post_init__(self):
        self.thumbnail_url = self.thumbnail_url.replace("{width}", "960").replace("{height}", "540")
        return self


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
    publishedAt: UTCDateTime
    thumbnails: YoutubeThumbnails
    localized: dict
    country: str | None = None


class ChannelStatistics(BaseModel):
    viewCount: int
    subscriberCount: int
    hiddenSubscriberCount: bool
    videoCount: int


class StreamSnippet(BaseModel):
    publishedAt: UTCDateTime
    channelId: str
    title: str
    description: str
    thumbnails: YoutubeThumbnails
    channelTitle: str
    liveBroadcastContent: str
    publishTime: UTCDateTime


class VideoSnippet(BaseModel):
    publishedAt: UTCDateTime
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
    actualStartTime: UTCDateTime | None = None
    actualEndTime: UTCDateTime | None = None
    scheduledStartTime: UTCDateTime | None = None
    scheduledEndTime: UTCDateTime | None = None
    concurrentViewers: int | None = None
    activeLiveChatId: str | None = None


class YoutubeChannel(BaseModel):
    kind: str
    etag: str
    id: str
    snippet: ChannelSnippet
    statistics: ChannelStatistics


class YouTubeStream(BaseModel):
    kind: str
    etag: str
    id: IdInfo
    snippet: StreamSnippet


class YoutubeVideo(BaseModel):
    kind: str
    etag: str
    id: str
    snippet: VideoSnippet
    liveStreamingDetails: LiveStreamingDetails | None = None

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
        return bool(self.liveStreamingDetails and self.liveStreamingDetails.actualStartTime and not self.liveStreamingDetails.actualEndTime and (nowtz() - self.liveStreamingDetails.actualStartTime) < timedelta(minutes=1))


class YoutubeRSSVideo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    link: HttpUrl
    yt_videoid: str
    yt_channelid: str
    title: str
    author_name: str = Field(alias="author")
    uplood_at: UTCDateTime = Field(alias="published")
    updated_at: UTCDateTime = Field(alias="updated")
    media_thumbnail: list[YoutubeThumbnail]


class YtSubscriptionDetails(BaseModel):
    callback_url: str
    state: str
    last_successful_verification: UTCDateTime
    expiration_time: UTCDateTime
    last_subscribe_request: UTCDateTime
    last_unsubscribe_request: UTCDateTime | None = None
    last_verification_error: UTCDateTime | None = None
    last_delivery_error: UTCDateTime | None = None
    last_item_delivered: UTCDateTime
    aggregate_statistics: str
    content_received: UTCDateTime | None = None
    content_delivered: UTCDateTime | None = None

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
    published_parsed: UTCDateTime  # 特殊處理
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
            return convert_tz(datetime(*v[:6], tzinfo=timezone.utc))
        if isinstance(v, dict):
            # 假如來的是 dict（像 JSON 會這樣），先轉成 tuple 再轉 datetime
            return convert_tz(datetime(*tuple(v.values())[:6]))
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
    createdAt: UTCDateTime
    description: str | None = None
    isVerified: bool
    likeCount: int
    followersCount: int
    followingsCount: int
    statusesCount: int
    pinnedTweet: str | None = None
    profileBanner: HttpUrl | None = None
    profileImage: HttpUrl | None = None
    location: str | None = None

    # @field_validator("createdAt", mode="before")
    # @classmethod
    # def parse_created_at(cls, v: str) -> datetime:
    #     return datetime.strptime(v, DATETIME_FORMAT)

    @property
    def url(self) -> str:
        return f"https://x.com/{self.userName}"


class RettiwtTweetEntity(BaseModel):
    hashtags: list[str | None] = Field(default_factory=list)
    mentionedUsers: list[str | None] = Field(default_factory=list)
    urls: list[str | None] = Field(default_factory=list)


class RettiwtTweetMedia(BaseModel):
    url: HttpUrl
    type: str


class RettiwtTweetItem(BaseModel):
    id: str
    conversationId: str
    createdAt: UTCDateTime
    tweetBy: RettiwtTweetUser
    entities: RettiwtTweetEntity
    media: list[RettiwtTweetMedia | None] = Field(default_factory=list)
    fullText: str
    lang: str
    quoteCount: int
    replyCount: int
    retweetCount: int
    likeCount: int
    viewCount: int | None = None
    bookmarkCount: int
    url: str

    # @property
    # def url(self) -> str:
    #     return f"https://twitter.com/{self.tweetBy.userName}/status/{self.id}"

    @property
    def is_retweet(self) -> bool:
        return self.fullText.startswith("RT @")


class RettiwtTweetTimeLineResponse(BaseModel):
    list: list[RettiwtTweetItem]
    next: str | None = None


class RettiwtTweetUserDetails(BaseModel):
    id: str
    userName: str
    fullName: str
    createdAt: UTCDateTime
    description: str
    isVerified: bool
    likeCount: int
    followersCount: int
    followingsCount: int
    statusesCount: int
    pinnedTweet: int | None = None
    profileBanner: HttpUrl | None = None
    profileImage: HttpUrl | None = None


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
    plain_text: str | None = None
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
    created_time: UTCDateTime | None = None
    # Created by property
    created_by: NotionUser | None = None
    # Last edited time property
    last_edited_time: UTCDateTime | None = None
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
            return convert_tz(datetime.fromisoformat(v.replace("Z", "+00:00")))
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
    created_time: UTCDateTime
    created_by: NotionUser
    last_edited_time: UTCDateTime
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
            return convert_tz(datetime.fromisoformat(v.replace("Z", "+00:00")))
        return v

    def get_plain_text(self):
        """從頁面屬性中提取純文本"""
        for prop_value in self.properties.values():
            if prop_value.type == "title" and prop_value.title:
                return prop_value.title[0].plain_text if prop_value.title else ""


class NotionDatabase(BaseModel):
    object: str
    id: str
    created_time: UTCDateTime
    created_by: NotionUser
    last_edited_time: UTCDateTime
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
            return convert_tz(datetime.fromisoformat(v.replace("Z", "+00:00")))
        return v


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
    created_time: UTCDateTime
    created_by: NotionUser
    last_edited_time: UTCDateTime
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
            return convert_tz(datetime.fromisoformat(v.replace("Z", "+00:00")))
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
