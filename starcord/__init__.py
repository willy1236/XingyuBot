'''
Discord機器人"星羽"用libary
'''

from .FileDatabase import Jsondb,csvdb
from .DataExtractor import sclient

from .utilities import *
from .errors import *
from starcord.core.classes import Cog_Extension

# if Jsondb.jdata.get('twitch_bot'):
#     from .clients.twitch_chatbot import twitch_bot
# else:
#     twitch_bot = None

__all__ = [
    'Jsondb',
    'csvdb',
    'log',
    'BotEmbed',
    'ChoiceList',
    'StarException',
    'mongedb',
    'sclient',
    'Cog_Extension',
]