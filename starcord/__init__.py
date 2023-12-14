'''
Discord機器人"星羽"用libary
'''

from .FileDatabase import Jsondb,csvdb
from .DataExtractor import sclient

from .utilities.utility import BotEmbed,BRS,ChoiceList
from .utilities.funtions import *
from .utilities.logger import create_logger
from .errors import StarException

file_log = Jsondb.jdata.get('file_log')
debug_mode = Jsondb.jdata.get("debug_mode",True)

from logging import INFO,DEBUG
log_level = DEBUG if debug_mode else INFO
log = create_logger('./logs',file_log,log_level)

# if Jsondb.jdata.get('twitch_bot'):
#     from .clients.twitch_chatbot import twitch_bot
# else:
#     twitch_bot = None

__all__ = [
    'Jsondb',
    'csvdb',
    'log',
    'BotEmbed',
    #'twitch_bot',
    'ChoiceList',
    'StarException',
    'mongedb',
    'sclient',
]