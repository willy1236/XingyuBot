import discord
from typing import TYPE_CHECKING
from starcord.types import DBGame
from starcord.utility import BotEmbed

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
    def __init__(self,data):
        self.data = [GameInfo(i) for i in data]
        self.discord_id = self.data[0].discord_id if self.data else None

    def desplay(self,dc_user:discord.User=None):
        if dc_user:
            title = dc_user.name
            thumbnail_url = dc_user.display_avatar.url
        else:
            title = self.discord_id
            thumbnail_url = discord.Embed.Empty
        
        embed = BotEmbed.simple(title=title)
        embed.set_thumbnail(url=thumbnail_url)
        
        for d in self.data:
            game = d.game.value
            name = d.player_name
            if name:
                embed.add_field(name=game, value=name, inline=False)
        
        return embed