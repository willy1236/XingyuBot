'''Discord機器人用lib庫
'''

#from . import model
from . import interface
from .database import *

#from .database import *
#from .file_database import *
from .utility import *
from .funtions import *
from .logger import create_logger


Jsondb = JsonDatabase()
SQLsettings = Jsondb.jdata.get('SQLsettings')
SQL_connection = Jsondb.jdata.get('SQL_connection')
file_log = Jsondb.jdata.get('file_log')

log = create_logger('./logs',file_log)

if SQL_connection:
    try:    
        sqldb = MySQLDatabase(**SQLsettings)
        log.info('>> SQL connect: on <<')
    except:
        log.warning('>> SQL connect: offline <<')
else:
    sqldb = None
    log.info('>> SQL connect: off <<')

assert isinstance(sqldb,MySQLDatabase),'sqldb is None'

__all__ = [
    'Jsondb',
    'sqldb',
    'log',
]