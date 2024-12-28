"""
### 模組：資料庫
處理資料庫連線與操作。
"""
from ..fileDatabase import Jsondb
from ..utils import log
from .mongodb import MongoDB
from .mysql import MySQLDatabase, SQLEngine

SQL_connection = Jsondb.config.get('SQL_connection')
def create_sqldb(should_connect:bool) -> MySQLDatabase | None:
    if should_connect:
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

def create_sqlengine(should_connect:bool) -> SQLEngine | None:
    if should_connect:
        try:
            from sqlalchemy.engine import URL

            SQLsettings = Jsondb.config["SQLsettings"]

            connection_url = URL.create(
                drivername="mysql+mysqlconnector",
                username=SQLsettings["user"],
                password=SQLsettings["password"],
                host=SQLsettings["host"],
                port=SQLsettings["port"]
            )
            sqlengine = SQLEngine(connection_url)
            version = sqlengine.engine.dialect.server_version_info
            log.info(f'>> SQL connect: online ({version}) <<')
        except Exception:
            sqlengine = None
            log.exception('>> SQL connect: offline <<')
    else:
        sqlengine = None
        log.info('>> SQL connect: off <<')
    
    return sqlengine

sqldb = create_sqlengine(SQL_connection)

Mongedb_connection = Jsondb.config.get('Mongedb_connection')
def create_mongedb(should_connect) -> MongoDB | None:
    if should_connect:
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