from datetime import date, datetime
from typing import TYPE_CHECKING

from ..Utilities import BotEmbed

class Party:
    __solts__ = ['id', 'name', 'role_id', 'creator_id', 'created_at', "member_count"]
    
    if TYPE_CHECKING:
        id: int
        name: str
        role_id: int
        creator_id: int
        created_at: date
        member_count: int | None

    def __init__(self, dct:dict):
        self.id = dct.get('party_id')
        self.name = dct.get('party_name')
        self.role_id = dct.get('role_id')
        self.creator_id = dct.get('creator_id')
        self.created_at = dct.get('created_at')
        self.member_count = dct.get('member_count')

    def __str__(self):
        return f'Party(id={self.id})'

    def __repr__(self):
        return self.__str__()
    
    def to_dict(self):
        return {
            'party_id': self.id,
            'party_name': self.name,
            'role_id': self.role_id,
            'creator_id': self.creator_id,
            'created_at': self.created_at,
            "member_count": self.member_count
        }
    
class BackupRoles:
    if TYPE_CHECKING:
        id: int
        name: str
        created_at: datetime
        guild_id: int
        colour_r: int
        colour_g: int
        colour_b: int
        description: str
        user_ids: list[int | None]

    def __init__(self, dct:dict, user_ids=[]):
        self.id = dct.get('role_id')
        self.name = dct.get('role_name')
        self.created_at = dct.get('created_at')
        self.guild_id = dct.get('guild_id')
        self.colour_r = dct.get('colour_r')
        self.colour_g = dct.get('colour_g')
        self.colour_b = dct.get('colour_b')
        self.description = dct.get('description')
        self.user_ids = user_ids
    
    def embed(self, bot):
        embed = BotEmbed.simple(self.name,self.description)
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
        