from core.classes import Cog_Extension
from discord.ext import commands

from BotLib.userlib import *
from BotLib.database import Database
from BotLib.basic import BotEmbed

class role_playing_game(Cog_Extension):
    pass
    

def setup(bot):
    bot.add_cog(role_playing_game(bot))