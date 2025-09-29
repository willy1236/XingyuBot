from datetime import datetime

import discord
from pydantic import AliasPath, BaseModel, ConfigDict, Field, HttpUrl, model_validator

from ..settings import tz


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
    published: datetime
    published_parsed: list[int]
    updated: datetime
    updated_parsed: list[int]
    thumbnail_url: HttpUrl | None = None

    @model_validator(mode="after")
    def __post_init__(self):
        self.published = self.published.astimezone(tz)
        self.updated = self.updated.astimezone(tz)
        self.thumbnail_url = f"https://i.ytimg.com/vi/{self.yt_videoid}/hqdefault.jpg"
        return self

    def embed(self):
        embed = discord.Embed(
            title=self.title,
            url=self.link,
            description=self.author_detail.name,
            color=0xff0000,
            timestamp = self.published
            )
        embed.add_field(name="上傳時間", value=self.published.strftime("%Y/%m/%d %H:%M:%S"), inline=False)
        embed.set_image(url=self.thumbnail_url)
        return embed


class Feed(BaseModel):
    links: list[LinkItem]
    title: str
    title_detail: TitleDetail
    updated: datetime
    updated_parsed: list[int]


class YoutubePushPost(BaseModel):
    bozo: bool
    entries: list[YoutubePushEntry]
    feed: Feed
    headers: dict = {}
    encoding: str
    version: str
    namespaces: dict[str, str]

