'''
Discord機器人"星羽"用libary
'''

#from . import model
from . import interface
from .database import Jsondb,sqldb,JsonDatabase
from .interface import UserClient

from .utility import BotEmbed,BRS,ChoiceList
from .funtions import *
from .logger import create_logger
from .errors import StarException


file_log = Jsondb.jdata.get('file_log')
log = create_logger('./logs',file_log)

if Jsondb.jdata.get('twitch_bot'):
    from .twitch_chatbot import twitch_bot
else:
    twitch_bot = None

__all__ = [
    'Jsondb',
    'sqldb',
    'log',
    'BotEmbed',
    'interface',
    'twitch_bot',
    'ChoiceList',
    'UserClient',
    'StarException',
]