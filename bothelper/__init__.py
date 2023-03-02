'''
Discord機器人用lib庫
'''

#from . import model
from . import interface
#from . import database
from .database import Jsondb,sqldb,JsonDatabase

from .utility import BotEmbed,BRS,ChoiceList
from .funtions import *
from .logger import create_logger


file_log = Jsondb.jdata.get('file_log')
log = create_logger('./logs',file_log)


__all__ = [
    'Jsondb',
    'sqldb',
    'log',
    'BotEmbed',
    'interface',
]