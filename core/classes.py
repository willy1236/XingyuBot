from discord.ext import commands
from BotLib.database import MySQLDatabase,JsonDatabase

try:
    SQLsettings = JsonDatabase().jdata["SQLsettings"]
    sqldb = MySQLDatabase(**SQLsettings)
    print('>> SQL connect: on <<')
except:
    print('>> SQL connect: off <<')

class Cog_Extension(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        try:
            self.sqldb = sqldb
        except:
            self.sqldb = None