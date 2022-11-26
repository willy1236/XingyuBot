from discord.ext import commands
from BotLib.database import MySQLDatabase,JsonDatabase


SQLsettings = JsonDatabase().jdata["SQLsettings"]
sqldb = MySQLDatabase(**SQLsettings)

class Cog_Extension(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        try:
            self.sqldb = sqldb
            #print('SQL connected')
        except:
            self.sqldb = None