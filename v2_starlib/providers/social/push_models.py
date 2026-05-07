from pydantic import AliasPath, BaseModel, ConfigDict, Field, HttpUrl, model_validator

from v2_starlib.base import UTCDateTime


class TitleDetail(BaseModel):
    type: str
    language: str | None
    base: str
    value: str


class LinkItem(BaseModel):
    rel: str
    href: HttpUrl
    type: str


class AuthorDetail(BaseModel):
    name: str
    href: HttpUrl


class YoutubePushEntry(BaseModel):
    id: str
    guidislink: bool
    link: HttpUrl
    yt_videoid: str
    yt_channelid: str
    title: str
    title_detail: TitleDetail
    links: list[LinkItem]
    authors: list[AuthorDetail]
    author_detail: AuthorDetail
    href: HttpUrl
    author: str
    published: UTCDateTime
    published_parsed: list[int]
    updated: UTCDateTime
    updated_parsed: list[int]
    thumbnail_url: HttpUrl | None = None

    @model_validator(mode="after")
    def __post_init__(self):
        self.thumbnail_url = f"https://i.ytimg.com/vi/{self.yt_videoid}/hqdefault.jpg"
        return self


class Feed(BaseModel):
    links: list[LinkItem]
    title: str
    title_detail: TitleDetail
    updated: UTCDateTime
    updated_parsed: list[int]


class YoutubePushPost(BaseModel):
    bozo: bool
    entries: list[YoutubePushEntry]
    feed: Feed
    headers: dict = {}
    encoding: str
    version: str
    namespaces: dict[str, str]
