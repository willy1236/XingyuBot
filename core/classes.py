import discord
from discord.ext import commands
from typing import TYPE_CHECKING
from starcord import sqldb

class Cog_Extension(commands.Cog):
    if TYPE_CHECKING:
        from starcord.database import MySQLDatabase
        sqldb: MySQLDatabase
    
    def __init__(self, bot:discord.Bot):
        self.bot = bot
        self.sqldb = sqldb