"""
### 模組：資料處理器
蒐集各來源資料並加以處理，同時提供操作以修改資料\n
由StarClient繼承並整合所有內容，使用者可直接調用sclient使用\n
### 各類別功能
sqldb: 存取與操作Mysql資料庫\n
各類client: 結合所有資料進行複雜操作\n
StarClient: 繼承所有內容，將基本（直接操作資料庫）及進階（clients）整合
"""
from starcord.FileDatabase import Jsondb
from .mysql import MySQLDatabase
from .cloud import MongoDB
from .client import StarClient

SQLsettings = Jsondb.jdata.get('SQLsettings')
SQL_connection = Jsondb.jdata.get('SQL_connection')

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

#sqldb = create_sqldb(SQL_connection)
sclient = StarClient(mysql_settings=SQLsettings)

Mongedb_connection = Jsondb.jdata.get('Mongedb_connection')


def create_mongedb(Mongedb_connection) -> MongoDB:
    if Mongedb_connection:
        url = Jsondb.get_token("mongodb_url")
        mongedb = MongoDB(url)
        print('>> MongoDB connect: on <<')
    else:
        mongedb = None
    return mongedb

mongedb = create_mongedb(Mongedb_connection)

#from .client import *
from .community import *
from .game import *
from .weather import *

__all__ =[
    'StarClient',
    'sclient',
    'MySQLDatabase',
    'TwitchAPI',
    'YoutubeAPI',
    'GoogleCloud',
    'NotionAPI',
    'RiotClient',
    'OsuInterface',
    'ApexInterface',
    'SteamInterface',
    'DBDInterface',
    'CWA_API',
]