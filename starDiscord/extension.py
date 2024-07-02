from typing import TYPE_CHECKING
from discord.ext import commands

if TYPE_CHECKING:
    from .bot import DiscordBot

class Cog_Extension(commands.Cog):
    def __init__(self, bot): 
        self.bot:DiscordBot = bot