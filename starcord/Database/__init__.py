"""
### 模組：資料庫
處理資料庫連線與操作。
"""
from ..FileDatabase import Jsondb
from ..Utilities import log

from .mysql import MySQLDatabase
from .mongodb import MongoDB

SQL_connection = Jsondb.jdata.get('SQL_connection')
def create_sqldb(SQL_connection:bool) -> MySQLDatabase:
    if SQL_connection:
        try:
            sqldb = MySQLDatabase(Jsondb.jdata.get('SQLsettings'))
            version = sqldb.connection.get_server_info()
            log.info(f'>> SQL connect: online ({version}) <<')
        except:
            sqldb = None
            log.warning('>> SQL connect: offline <<')
    else:
        sqldb = None
        log.info('>> SQL connect: off <<')
    
    return sqldb

sqldb = create_sqldb(SQL_connection)

Mongedb_connection = Jsondb.jdata.get('Mongedb_connection')
def create_mongedb(Mongedb_connection) -> MongoDB:
    if Mongedb_connection:
        url = Jsondb.get_token("mongodb_url")
        mongedb = MongoDB(url)
        log.info('>> MongoDB connect: on <<')
    else:
        mongedb = None
    return mongedb

mongedb = create_mongedb(Mongedb_connection)

__all__ = [
    'MySQLDatabase',
    'sqldb',
]