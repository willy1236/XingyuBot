import discord
from discord.ext import commands
from starcord.FileDatabase import Jsondb

class DiscordBot(discord.Bot):
    def __init__(self,bot_code):
        super().__init__(
            owner_id = 419131103836635136,
            intents = discord.Intents.all(),
            help_command = None
        )
        
        self.bot_code = bot_code
        self.main_guilds = Jsondb.jdata.get('main_guild')
        self.debug_mode = Jsondb.jdata.get('debug_mode',True)

        if bot_code != 'Bot1':
            self.debug_guilds = Jsondb.jdata.get('debug_guild')

    def run(self):
        token = Jsondb.get_token(self.bot_code)
        super().run(token)

class Cog_Extension(commands.Cog):
    def __init__(self, bot:DiscordBot): 
        self.bot = bot