"""
### 模組：資料庫
處理資料庫連線與操作。
"""
from ..fileDatabase import Jsondb
from ..utils import log
from .mongodb import MongoDB
from .mysql import SQLEngine

debug_mode = Jsondb.config.get("debug_mode",True)
SQL_connection = Jsondb.config.get('SQL_connection')

def create_sqlengine(connect_name:str | None) -> SQLEngine:
    if connect_name:
        SQLsettings = Jsondb.config.get(connect_name)
    else:
        SQLsettings = None
    
    if SQLsettings is not None:
        try:
            from sqlalchemy.engine import URL
            
            connection_url = URL.create(
                #drivername="mysql+mysqlconnector",
                drivername="postgresql",
                username=SQLsettings["user"],
                password=SQLsettings["password"],
                host=SQLsettings["host"],
                port=SQLsettings["port"],
                database=SQLsettings["database"],
            )
            sqlengine = SQLEngine(connection_url)
            name = sqlengine.engine.dialect.name
            version = sqlengine.engine.dialect.server_version_info
            log.info(f'>> SQL connect: online ({name}, {version}, {SQLsettings["user"]} in {SQLsettings["host"]}) <<')
        except Exception:
            sqlengine = None
            log.exception('>> SQL connect: offline <<')
    else:
        sqlengine = None
        log.info('>> SQL connect: off <<')
    
    return sqlengine # type: ignore

sqldb = create_sqlengine(SQL_connection)

Mongedb_connection = Jsondb.config.get('Mongedb_connection')
def create_mongedb(should_connect) -> MongoDB:
    if should_connect:
        url = Jsondb.get_token("mongodb_url")
        mongedb = MongoDB(url)
        log.info('>> MongoDB connect: on <<')
    else:
        mongedb = None
    return mongedb # type: ignore

mongedb = create_mongedb(Mongedb_connection)

__all__ = [
    'sqldb',
]