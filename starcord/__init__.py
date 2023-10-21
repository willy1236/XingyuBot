'''
Discord機器人"星羽"用libary
'''

from . import clients
from .database import Jsondb,sqldb,mongedb
from .clients import StarClient

from .utility import BotEmbed,BRS,ChoiceList
from .funtions import *
from .logger import create_logger
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

sclient = StarClient()

__all__ = [
    'Jsondb',
    'sqldb',
    'log',
    'BotEmbed',
    'clients',
    #'twitch_bot',
    'ChoiceList',
    'StarException',
    'mongedb',
    'sclient',
]