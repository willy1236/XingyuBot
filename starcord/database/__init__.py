'''
資料庫操作與管理
'''

from .file import *
from .mysql import MySQLDatabase

Jsondb = JsonDatabase()
SQLsettings = Jsondb.jdata.get('SQLsettings')
SQL_connection = Jsondb.jdata.get('SQL_connection')
file_log = Jsondb.jdata.get('file_log')

if SQL_connection:
    try:    
        sqldb = MySQLDatabase(**SQLsettings)
        #log.info('>> SQL connect: on <<')
        print(('>> SQL connect: on <<'))
    except:
        #log.warning('>> SQL connect: offline <<')
        sqldb = None
        print('>> SQL connect: offline <<')
else:
    #log.info('>> SQL connect: off <<')
    print('>> SQL connect: off <<')


#assert isinstance(sqldb,MySQLDatabase),'sqldb is None'

__all__ = [
    'JsonDatabase',
    'MySQLDatabase',
    'sqldb',
    'Jsondb',
]
