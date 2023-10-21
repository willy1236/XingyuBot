'''
資料庫操作與管理
'''

from .file import *
from .mysql import MySQLDatabase
from .cloud import MongoDB

Jsondb = JsonDatabase()
SQLsettings = Jsondb.jdata.get('SQLsettings')
SQL_connection = Jsondb.jdata.get('SQL_connection')
file_log = Jsondb.jdata.get('file_log')
Mongedb_connection = Jsondb.jdata.get('Mongedb_connection')

csvdb = CsvDatabase()

def create_sqldb(SQL_connection:bool) -> MySQLDatabase:
    if SQL_connection:
        try:
            sqldb = MySQLDatabase(SQLsettings)
            #log.info('>> SQL connect: on <<')
            print('>> MySQL connect: on <<')
        except:
            #log.warning('>> SQL connect: offline <<')
            sqldb = None
            print('>> MySQL connect: offline <<')
    else:
        #log.info('>> SQL connect: off <<')
        sqldb = None
        print('>> MySQL connect: off <<')
    
    return sqldb

sqldb = create_sqldb(SQL_connection)

def create_mongedb(Mongedb_connection) -> MongoDB:
    if Mongedb_connection:
        url = Jsondb.get_token("mongodb_url")
        mongedb = MongoDB(url)
        print('>> MongoDB connect: on <<')
    else:
        mongedb = None
    return mongedb

mongedb = create_mongedb(Mongedb_connection)

#assert isinstance(sqldb,MySQLDatabase),'sqldb is None'

__all__ = [
    'JsonDatabase',
    'MySQLDatabase',
    'sqldb',
    'Jsondb',
    'mongedb',
]
