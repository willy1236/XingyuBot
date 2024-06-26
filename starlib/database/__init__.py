"""
### 模組：資料庫
處理資料庫連線與操作。
"""
from ..fileDatabase import Jsondb
from ..utilities import log

from .mysql import MySQLDatabase
from .mongodb import MongoDB

SQL_connection = Jsondb.config.get('SQL_connection')
def create_sqldb(SQL_connection:bool) -> MySQLDatabase | None:
    if SQL_connection:
        try:
            sqldb = MySQLDatabase(Jsondb.config.get('SQLsettings'))
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

Mongedb_connection = Jsondb.config.get('Mongedb_connection')
def create_mongedb(Mongedb_connection) -> MongoDB | None:
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