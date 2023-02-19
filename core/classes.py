import discord
from discord.ext import commands
from bothelper import sqldb
from bothelper.database.mysql import MySQLDatabase

class Cog_Extension(commands.Cog):
    def __init__(self, bot:discord.Bot):
        self.bot = bot
        self.sqldb: MySQLDatabase = sqldb