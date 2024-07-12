from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, TypedDict, TYPE_CHECKING

from discord import Bot

from ..settings import tz
from ..types import NotifyCommunityType, WarningType
from ..utilities import BotEmbed,ChoiceList
from .BaseModel import ListObject
from ..fileDatabase import Jsondb


@dataclass(slots=True)
class Party():
    id: int
    name: str
    role_id: int
    creator_id: int
    created_at: date
    member_count: Optional[int]
    
@dataclass(slots=True)
class BackupRoles:
    role_id: int
    role_name: str
    created_at: datetime
    guild_id: int
    colour_r: int
    colour_g: int
    colour_b: int
    description: str
    user_ids: list[Optional[int]] = field(default_factory=list)

    def __post_init__(self):
        self.created_at = self.created_at.replace(tzinfo=tz)
    
    def embed(self, bot):
        embed = BotEmbed.simple(self.role_name,self.description)
        embed.add_field(name="創建於", value=self.created_at.strftime("%Y/%m/%d %H:%M:%S"))
        embed.add_field(name="顏色", value=f"({self.colour_r}, {self.colour_g}, {self.colour_b})")
        if self.user_ids and bot:
            user_list = []
            for user_id in self.user_ids:
                user = bot.get_user(user_id)
                if user:
                    user_list.append(user.mention)
            embed.add_field(name="成員", value=",".join(user_list),inline=False)

        return embed

@dataclass(slots=True)
class NotifyChannelRecords:
    guild_id: int
    notify_type: str
    channel_id: int
    role_id: int

@dataclass(slots=True)
class NotifyCommunityRecords:
    notify_type: NotifyCommunityType 
    notify_name: str
    display_name: str
    guild_id: int
    channel_id: int
    role_id: int

    def __post_init__(self):
        self.notify_type = NotifyCommunityType(self.notify_type)

@dataclass(slots=True)
class WarningSheet:
    warning_id: int
    discord_id: int
    moderate_type: WarningType
    moderate_user: int
    create_guild: int
    create_time: datetime
    reason: str
    last_time: str
    guild_only: bool
    officially_given: bool = None
    bot_given: bool = None

    def __post_init__(self):
        self.create_time = self.create_time.replace(tzinfo=tz)
        self.moderate_type = WarningType(self.moderate_type)
        self.officially_given = self.create_guild in Jsondb.config["debug_guilds"]
    
    def embed(self,bot:Bot):
        user = bot.get_user(self.discord_id)
        moderate_user = bot.get_user(self.moderate_user)
        guild = bot.get_guild(self.create_guild)
        
        name = f'{user.name} 的警告單'
        description = f"**編號:{self.warning_id} ({ChoiceList.get_tw(self.moderate_type,'warning_type')})**\n被警告用戶：{user.mention}\n管理員：{guild.name}/{moderate_user.mention}\n原因：{self.reason}\n時間：{self.create_time}"
        if self.officially_given:
            description += "\n官方警告"
        if self.guild_only:
            description += "\n伺服器區域警告"
        embed = BotEmbed.general(name=name,icon_url=user.display_avatar.url,description=description)
        return embed
    
    def display_embed_field(self,bot:Bot):
            moderate_user = bot.get_user(self.moderate_user)
            guild = bot.get_guild(self.create_guild)
            name = f"編號: {self.warning_id} ({ChoiceList.get_tw(self.moderate_type,'warning_type')})"
            value = f"{guild.name}/{moderate_user.mention}\n{self.reason}\n{self.create_time}"
            if self.officially_given:
                value += "\n官方警告"
            if self.guild_only:
                value += "\n伺服器區域警告"
            return name, value
    
    # def remove(self):
    #     self.sqldb.remove_warning(self.warning_id)

class WarningList(ListObject):
    if TYPE_CHECKING:
        items: list[WarningSheet]
        discord_id: int

    def __init__(self,data:dict,discord_id:int,sqldb=None):
        super().__init__([WarningSheet(**i) for i in data])
        self.discord_id = discord_id
    
    def display(self,bot:Bot):
        user = bot.get_user(self.discord_id)
        embed = BotEmbed.general(f'{user.name} 的警告單列表（共{len(self)}筆）',user.display_avatar.url)
        for i in self.items:
            name, value = i.display_embed_field(bot)
            embed.add_field(name=name,value=value)
        return embed

@dataclass(slots=True)
class DiscordRegisterationRecord:
    registrations_id: int
    guild_id: int
    role_id: int
