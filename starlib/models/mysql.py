from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, TypedDict

from ..settings import tz
from ..types import NotifyCommunityType
from ..utilities import BotEmbed


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
class NotifyCommunityRecords:
    notify_type: NotifyCommunityType 
    notify_name: str
    display_name: str
    guild_id: int
    channel_id: int
    role_id: int

    def __post_init__(self):
        self.notify_type = NotifyCommunityType(self.notify_type)