from discord.ext import commands
from BotLib.database import MySQLDatabase,JsonDatabase

jdata = JsonDatabase().jdata
SQL_connection = jdata.get('SQL_connection')

if SQL_connection:
    try:    
        SQLsettings = jdata["SQLsettings"]
        sqldb = MySQLDatabase(**SQLsettings)
        print('>> SQL connect: on <<')
    except:
        print('>> SQL connect: offline <<')
else:
    print('>> SQL connect: off <<')

class Cog_Extension(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        try:
            self.sqldb = sqldb
        except:
            self.sqldb = None