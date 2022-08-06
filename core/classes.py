from discord.ext import commands
from BotLib.database import SQLDatabase,Database

class Cog_Extension(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        try:
            SQLsettings = Database().jdata["SQLsettings"]
            self.sqldb = SQLDatabase(**SQLsettings)
            #print('SQL connected')
        except:
            self.sqldb = None