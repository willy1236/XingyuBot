import discord
from discord.ext import commands
from bothelper import sqldb

class Cog_Extension(commands.Cog):
    def __init__(self, bot:discord.Bot):
        self.bot = bot
        try:
            self.sqldb = sqldb
        except:
            self.sqldb = None