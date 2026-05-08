from discord.ext import commands

from .bot import DiscordBot


class Cog_Extension(commands.Cog):
    def __init__(self, bot: DiscordBot):
        self.bot: DiscordBot = bot
