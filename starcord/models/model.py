import discord,datetime
from typing import TYPE_CHECKING
from starcord.types import DBGame
from starcord.utilities.utility import BotEmbed
from starcord.FileDatabase import Jsondb

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

class GameInfoPage:
    def __init__(self,data=None):
        self.data = [GameInfo(i) for i in data] if data else []
        self.discord_id = self.data[0].discord_id if self.data else None

    def desplay(self,dc_user:discord.User=None):
        if dc_user:
            title = dc_user.name + " 遊戲資料"
            thumbnail_url = dc_user.display_avatar.url
        else:
            title = self.discord_id + " 遊戲資料"
            thumbnail_url = discord.Embed.Empty
        
        embed = BotEmbed.simple(title=title)
        embed.set_thumbnail(url=thumbnail_url)
        
        for d in self.data:
            game = d.game.value
            name = d.player_name
            if name:
                embed.add_field(name=game, value=name, inline=False)
        
        return embed
    
class WarningSheet:
    if TYPE_CHECKING:
        from starcord.DataExtractor.client import StarClient
        sclient: StarClient
        warning_id: int
        discord_id: int
        moderate_user_id: int
        guild_id: int
        create_time: datetime.datetime
        moderate_type: str
        reason: str
        last_time: str
        officially_given: bool
        bot_given: bool
    
    def __init__(self,data:dict,sclient=None):
        self.sclient = sclient
        self.warning_id = data.get("warning_id")
        self.discord_id = data.get("discord_id")
        self.moderate_user_id = data.get("moderate_user")
        self.guild_id = data.get("create_guild")
        self.create_time = data.get("create_time")
        self.moderate_type = data.get("moderate_type")
        self.reason = data.get("reason")
        self.last_time = data.get("last_time")
        self.bot_given = data.get("bot_given")

    @property
    def officially_given(self):
        return self.guild_id in Jsondb.jdata["debug_guild"]
    
    def display(self,bot:discord.Bot):
        user = bot.get_user(self.discord_id)
        moderate_user = bot.get_user(self.moderate_user_id)
        guild = bot.get_guild(self.guild_id)
        
        name = f'{user.name} 的警告單'
        description = f"**編號:{self.warning_id} ({self.moderate_type})**\n被警告用戶：{user.mention}\n管理員：{guild.name}/{moderate_user.mention}\n原因：{self.reason}\n時間：{self.create_time}"
        if self.officially_given:
            description += "\n機器人官方給予"
        embed = BotEmbed.general(name=name,icon_url=user.display_avatar.url,description=description)
        return embed