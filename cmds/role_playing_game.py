from core.classes import Cog_Extension
from BotLib.user import *
from BotLib.database import Database
from BotLib.basic import BotEmbed

class role_playing_game(Cog_Extension):
    picdata = Database().picdata
    jdata = Database().jdata
    


def setup(bot):
    bot.add_cog(role_playing_game(bot))