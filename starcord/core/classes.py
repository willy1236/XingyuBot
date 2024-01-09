import discord
from discord.ext import commands

class Cog_Extension(commands.Cog):
    def __init__(self, bot:discord.Bot):
        self.bot = bot