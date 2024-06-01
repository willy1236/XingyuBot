import discord
from discord.ext import commands
from starcord.fileDatabase import Jsondb

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

#commands.Bot
#shard_count=1,
#command_prefix=commands.when_mentioned_or('b!'),
#command_prefix='b!',
#case_insensitive=True,

class Cog_Extension(commands.Cog):
    def __init__(self, bot:DiscordBot): 
        self.bot = bot