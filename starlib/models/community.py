import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import discord

from ..fileDatabase import Jsondb
from ..settings import tz
from ..utilities import BotEmbed


class TwitchUser():
    def __init__(self,data:dict):
        self.id = data.get("id")
        self.login = data.get("login")
        self.display_name = data.get("display_name")
        self.type = data.get("type")
        self.broadcaster_type = data.get("broadcaster_type")
        self.description = data.get("description")
        self.profile_image_url = data.get("profile_image_url")
        self.offline_image_url = data.get("offline_image_url")
        self.view_count = data.get("view_count")
        self.email = data.get("email")
        self.created_at = data.get("created_at")
        self.url = f"https://www.twitch.tv/{self.login}"

    def desplay(self):
        embed = discord.Embed(
            title=self.display_name,
            url=self.url,
            description=self.description,
            color=0x6441a5,
            timestamp = datetime.now()
            )
        embed.set_image(url=self.offline_image_url)
        embed.set_author(name=self.login,icon_url=self.profile_image_url)
        embed.add_field(name="觀看數",value=self.view_count)
        embed.add_field(name="頻道創建日期",value=self.created_at)
        #embed.add_field(name="聯絡郵件",value=self.email)
        embed.set_footer(text=self.id)
        return embed

@dataclass(slots=True)
class TwitchStream():
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
    tag_ids: list[str]
    tags: list[str]
    is_mature: bool
    url: str = field(init=False)

    def __post_init__(self):
        self.thumbnail_url = self.thumbnail_url.replace('{width}','960').replace('{height}','540')
        self.started_at = datetime.strptime(self.started_at,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).astimezone(tz=tz)
        self.url = f"https://www.twitch.tv/{self.user_login}"

    def embed(self):
        embed = discord.Embed(
            title=self.title,
            url=self.url,
            description=self.game_name,
            color=0x6441a5,
            timestamp = datetime.now(),
            icon_url = Jsondb.picdata["twitch_001"]
            )
        embed.set_author(name=f"{self.username} 開台啦！")
        embed.set_image(url=self.thumbnail_url)
        embed.add_field(name="標籤",value=", ".join(self.tags))
        embed.set_footer(text=f"開始於 {self.starttime.strftime('%Y/%m/%d %H:%M:%S')}")
        return embed

class TwitchVideo():
    def __init__(self,data:dict):
        self.video_id = data.get("id")
        self.stream_id = data.get("stream_id")
        self.user_id = data.get("user_id")
        self.user_login = data.get("user_login")
        self.user_name = data.get("user_name")
        self.title = data.get("title")
        self.description = data.get("description")
        self.created_at = datetime.strptime(data.get('created_at'),'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).astimezone(tz=tz)
        self.published_at = datetime.strptime(data.get('published_at'),'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).astimezone(tz=tz)
        self.url = data.get("url")
        self.thumbnail_url = data.get("thumbnail_url").replace('{width}','960').replace('{height}','540')
        self.view_count = data.get("view_count")
        self.duration = data.get("duration")
    
    def embed(self):
        embed = discord.Embed(
            title=self.title,
            url=self.url,
            description=self.description,
            color=0x6441a5
            )
        embed.set_author(name=f"{self.user_name}")
        embed.set_image(url=self.thumbnail_url)
        embed.set_footer(text=f"上傳時間 {self.created_at.strftime('%Y/%m/%d %H:%M:%S')}")
        return embed

class TwitchClip():
    def __init__(self,data:dict):
        self.clip_id = data.get("id")
        self.broadcaster_id = data.get("broadcaster_id")
        self.broadcaster_name = data.get("broadcaster_name")
        self.creator_id = data.get("creator_id")
        self.creator_name = data.get("creator_name")
        self.video_id = data.get("video_id")
        self.game_id = data.get("game_id")
        self.language = data.get("language")
        self.title = data.get("title")
        self.view_count = data.get("view_count")
        self.created_at = datetime.strptime(data.get('created_at'),'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).astimezone(tz=tz)
        self.thumbnail_url = data.get("thumbnail_url").replace('{width}','960').replace('{height}','540')
        self.url = data.get("url")
        self.duration = timedelta(seconds=data.get("duration"))
    
    def embed(self):
        embed = discord.Embed(
            title=self.title,
            url=self.url,
            color=0x6441a5
            )
        embed.set_author(name=f"{self.broadcaster_name}")
        embed.set_image(url=self.thumbnail_url)
        embed.add_field(name="剪輯者",value=self.creator_name)
        embed.set_footer(text=f"上傳時間 {self.created_at.strftime('%Y/%m/%d %H:%M:%S')}")
        return embed

class YoutubeChannel:
    if TYPE_CHECKING:
        id: str
        title: str
        description: str
        customUrl: str
        publishedAt: datetime
        thumbnails_default: str
        thumbnails_medium: str
        thumbnails_high: str
        viewCount: int
        subscriberCount: int
        hiddenSubscriberCount: bool
        videoCount: int

    def __init__(self,data:dict):
        self.id = data.get('id')
        
        self.title = data.get('snippet').get('title')
        self.description = data.get('snippet').get('description')
        self.customUrl = data.get('snippet').get('customUrl')
        self.publishedAt = datetime.fromisoformat(data.get('snippet').get('publishedAt'))
        
        self.thumbnails_default = data.get('snippet').get('thumbnails').get('default').get('url')
        self.thumbnails_medium = data.get('snippet').get('thumbnails').get('medium').get('url')
        self.thumbnails_high = data.get('snippet').get('thumbnails').get('high').get('url')

        self.viewCount = int(data.get('statistics').get('viewCount'))
        self.subscriberCount = int(data.get('statistics').get('subscriberCount'))
        self.hiddenSubscriberCount = data.get('statistics').get('hiddenSubscriberCount')
        self.videoCount = int(data.get('statistics').get('videoCount'))

    def embed(self):
        embed = discord.Embed(
            title=self.title,
            url=f"https://www.youtube.com/channel/{self.id}",
            description=self.description,
            color=0xff0000,
            timestamp = datetime.now()
            )
        embed.set_image(url=self.thumbnails_default)
        embed.add_field(name="頻道創建時間",value=self.publishedAt.strftime('%Y/%m/%d %H:%M:%S'))
        embed.add_field(name="訂閱數",value=f"{self.subscriberCount:,}")
        embed.add_field(name="影片數",value=f"{self.videoCount:,}")
        embed.add_field(name="觀看數",value=f"{self.viewCount:,}")
        embed.add_field(name="用戶代碼",value=self.customUrl)
        embed.set_footer(text=self.id)
        return embed

class YouTubeStream:
    def __init__(self,data:dict):
        self.publishedAt = data.get('snippet').get('publishedAt')
        self.channelId = data.get('snippet').get('channelId')
        self.title = data.get('snippet').get('title')
        self.description = data.get('snippet').get('description')

        self.thumbnails_default = data.get('snippet').get('thumbnails').get('default').get('url')
        self.thumbnails_medium = data.get('snippet').get('thumbnails').get('medium').get('url')
        self.thumbnails_high = data.get('snippet').get('thumbnails').get('high').get('url')

class YoutubeVideo:
    def __init__(self,data:dict):
        self.id = data.get('yt_videoid')
        self.title = data.get("title")
        self.author_name = data.get("author")
        self.link = data.get("link")
        self.media_thumbnail_url = data.get("media_thumbnail")[0].get('url')
        self.uplood_at = datetime.fromtimestamp(time.mktime(data["published_parsed"]),tz=timezone.utc).replace(tzinfo=tz)
        self.updated_at = datetime.fromtimestamp(time.mktime(data["updated_parsed"]),tz=timezone.utc).replace(tzinfo=tz)
        self.author = data.get("authors")[0].get("name")
        
    def embed(self):
        embed = BotEmbed.simple(self.title,self.author_name,url=self.link)
        embed.add_field(name="上傳時間",value=self.uplood_at.strftime('%Y/%m/%d %H:%M:%S'),inline=False)
        embed.add_field(name="更新時間",value=self.updated_at.strftime('%Y/%m/%d %H:%M:%S'),inline=True)
        embed.set_image(url=self.media_thumbnail_url)
        return embed