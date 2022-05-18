import discord
from discord.ext import commands
from BotLib.database import Database

class Cog_Extension(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.jdata = Database().jdata