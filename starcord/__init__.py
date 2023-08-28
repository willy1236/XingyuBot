'''
Discord機器人"星羽"用libary
'''

#from . import model
from . import clients
from .database import Jsondb,sqldb,mongedb
from .clients import UserClient,NoticeClient

from .utility import BotEmbed,BRS,ChoiceList
from .funtions import *
from .logger import create_logger
from .errors import StarException

file_log = Jsondb.jdata.get('file_log')
log = create_logger('./logs',file_log)

# if Jsondb.jdata.get('twitch_bot'):
#     from .clients.twitch_chatbot import twitch_bot
# else:
#     twitch_bot = None

nclient = NoticeClient()

__all__ = [
    'Jsondb',
    'sqldb',
    'log',
    'BotEmbed',
    'clients',
    #'twitch_bot',
    'ChoiceList',
    'UserClient',
    'StarException',
    'mongedb',
    'nclient',
]