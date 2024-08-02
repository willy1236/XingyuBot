from datetime import datetime

import discord
from pydantic import AliasPath, BaseModel, ConfigDict, Field, model_validator

from ..settings import tz


class YoutubePush(BaseModel):
    model_config = ConfigDict(extra='ignore')

    id: str
    yt_videoid: str
    yt_channelid: str
    title: str
    link: str
    author_name: str = Field(validation_alias=AliasPath('authors', '0', 'name'))
    author_uri: str  = Field(validation_alias=AliasPath('authors', '0', 'href'))
    published: datetime
    updated: datetime
        
    @model_validator(mode='after')
    def __post_init__(self):
        self.published = self.published.astimezone(tz)
        self.updated = self.updated.astimezone(tz)

    def embed(self):
        embed = discord.Embed(
            title=self.title,
            url=self.link,
            description=self.author_name,
            color=0xff0000,
            timestamp = self.published
            )
        embed.add_field(name="上傳時間",value=self.published.strftime('%Y/%m/%d %H:%M:%S'),inline=False)
        return embed
    