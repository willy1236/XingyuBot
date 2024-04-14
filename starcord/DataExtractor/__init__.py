"""
### 模組：資料處理器
蒐集各來源資料並加以處理，同時提供操作以修改資料\n
由StarClient繼承並整合所有內容，使用者可直接調用sclient使用\n
### 各類別功能
sqldb: 存取與操作Mysql資料庫\n
"""
from ..FileDatabase import Jsondb
from ..Utilities import log
from .mysql import MySQLDatabase
from .cloud import MongoDB

from .community import *
from .game import *
from .weather import *

SQL_connection = Jsondb.jdata.get('SQL_connection')
def create_sqldb(SQL_connection:bool) -> MySQLDatabase:
    if SQL_connection:
        try:
            sqldb = MySQLDatabase(Jsondb.jdata.get('SQLsettings'))
            log.info('>> SQL connect: on <<')
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

__all__ =[
    'MySQLDatabase',
    'TwitchAPI',
    'YoutubeAPI',
    'GoogleCloud',
    'NotionAPI',
    'RiotAPI',
    'OsuInterface',
    'ApexInterface',
    'SteamInterface',
    'DBDInterface',
    'CWA_API',
]