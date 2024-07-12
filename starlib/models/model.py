from datetime import datetime
from typing import TYPE_CHECKING

import discord

from .BaseModel import ListObject
from ..types import DBGame
from ..utilities.utility import BotEmbed
from ..fileDatabase import Jsondb
from ..settings import tz

if TYPE_CHECKING:
    from starlib.database import MySQLDatabase

class GameInfo:
    if TYPE_CHECKING:
        discord_id: int
        game: DBGame
        player_name: str
        player_id: str
        account_id: str
        other_id: str
    
    def __init__(self,data):
        self.discord_id = data.get("discord_id")
        self.game = DBGame(data.get("game"))
        self.player_name = data.get("player_name")
        self.player_id = data.get("player_id")
        self.account_id = data.get("account_id")
        self.other_id = data.get("other_id")

class GameInfoPage():
    def __init__(self,data=None):
        self.items = [GameInfo(i) for i in data] if data else []
        self.discord_id = self.items[0].discord_id if self.items else None

    def embed(self,dc_user:discord.User=None):
        if dc_user:
            title = dc_user.name + " 遊戲資料"
            thumbnail_url = dc_user.display_avatar.url
        else:
            title = self.discord_id + " 遊戲資料"
            thumbnail_url = None
        
        embed = BotEmbed.simple(title=title)
        embed.set_thumbnail(url=thumbnail_url)
        
        for d in self.items:
            game = d.game.value
            name = d.player_name
            if name:
                embed.add_field(name=game, value=name, inline=False)
        
        return embed

