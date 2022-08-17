from discord.ext import commands
from BotLib.database import SQLDatabase,Database


SQLsettings = Database().jdata["SQLsettings"]
sqldb = SQLDatabase(**SQLsettings)

class Cog_Extension(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        try:
            self.sqldb = sqldb
            #print('SQL connected')
        except:
            self.sqldb = None