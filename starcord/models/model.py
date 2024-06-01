from datetime import datetime
from typing import TYPE_CHECKING

import discord

from .BaseModel import ListObject
from ..types import DBGame
from ..utilities.utility import BotEmbed
from ..fileDatabase import Jsondb
from ..settings import tz

if TYPE_CHECKING:
    from starcord.database import MySQLDatabase

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
    
class WarningSheet:
    if TYPE_CHECKING:
        sqldb: MySQLDatabase
        warning_id: int
        discord_id: int
        moderate_user_id: int
        guild_id: int
        create_time: datetime
        moderate_type: str
        reason: str
        last_time: str
        guild_only: bool
        officially_given: bool
        bot_given: bool
    
    def __init__(self,data:dict,sqldb=None):
        self.sqldb = sqldb
        self.warning_id = data.get("warning_id")
        self.discord_id = data.get("discord_id")
        self.moderate_user_id = data.get("moderate_user")
        self.guild_id = data.get("create_guild")
        self.create_time = data.get("create_time")
        self.moderate_type = data.get("moderate_type")
        self.reason = data.get("reason")
        self.last_time = data.get("last_time")
        self.guild_only = data.get("guild_only")
        self.bot_given = data.get("bot_given")

        self.__officially_given = None

        if isinstance(self.create_time,datetime):
            self.create_time.replace(tzinfo=tz)

    @property
    def officially_given(self):
        if self.__officially_given is None:
            self.__officially_given = self.guild_id in Jsondb.jdata["debug_guild"]
        return self.__officially_given
    
    def embed(self,bot:discord.Bot):
        user = bot.get_user(self.discord_id)
        moderate_user = bot.get_user(self.moderate_user_id)
        guild = bot.get_guild(self.guild_id)
        
        name = f'{user.name} 的警告單'
        description = f"**編號:{self.warning_id} ({self.moderate_type})**\n被警告用戶：{user.mention}\n管理員：{guild.name}/{moderate_user.mention}\n原因：{self.reason}\n時間：{self.create_time}"
        if self.officially_given:
            description += "\n官方警告"
        if self.guild_only:
            description += "\n伺服器區域警告"
        embed = BotEmbed.general(name=name,icon_url=user.display_avatar.url,description=description)
        return embed
    
    def display_embed_field(self,bot:discord.Bot):
            moderate_user = bot.get_user(self.moderate_user_id)
            guild = bot.get_guild(self.guild_id)
            name = f"編號: {self.warning_id} ({self.moderate_type})"
            value = f"{guild.name}/{moderate_user.mention}\n{self.reason}\n{self.create_time}"
            if self.officially_given:
                value += "\n官方警告"
            if self.guild_only:
                value += "\n伺服器區域警告"
            return name, value
    
    def remove(self):
        self.sqldb.remove_warning(self.warning_id)

class WarningList(ListObject):
    if TYPE_CHECKING:
        items: list[WarningSheet]
        discord_id: int

    def __init__(self,data:dict,discord_id:int,sqldb=None):
        super().__init__([WarningSheet(i,sqldb) for i in data])
        self.discord_id = discord_id
    
    def display(self,bot:discord.Bot):
        user = bot.get_user(self.discord_id)
        embed = BotEmbed.general(f'{user.name} 的警告單列表（共{len(self)}筆）',user.display_avatar.url)
        for i in self.items:
            name, value = i.display_embed_field(bot)
            embed.add_field(name=name,value=value)
        return embed
