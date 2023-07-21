'''
資料庫操作與管理
'''

from .file import *
from .mysql import MySQLDatabase

Jsondb = JsonDatabase()
SQLsettings = Jsondb.jdata.get('SQLsettings')
SQL_connection = Jsondb.jdata.get('SQL_connection')
file_log = Jsondb.jdata.get('file_log')


def create_sqldb(SQL_connection:bool) -> MySQLDatabase:
    if SQL_connection:
        try:
            sqldb = MySQLDatabase(**SQLsettings)
            #log.info('>> SQL connect: on <<')
            print('>> SQL connect: on <<')
        except:
            #log.warning('>> SQL connect: offline <<')
            sqldb = None
            print('>> SQL connect: offline <<')
    else:
        #log.info('>> SQL connect: off <<')
        sqldb = None
        print('>> SQL connect: off <<')
    
    return sqldb

sqldb = create_sqldb(SQL_connection)



#assert isinstance(sqldb,MySQLDatabase),'sqldb is None'

__all__ = [
    'JsonDatabase',
    'MySQLDatabase',
    'sqldb',
    'Jsondb',
]
