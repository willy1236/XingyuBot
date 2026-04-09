"""
### 模組：資料庫
處理資料庫連線與操作。
"""
from starlib.fileDatabase import Jsondb
from starlib.utils import log

from .mongodb.client import MongoDB
from .postgresql.client import SQLRepository, create_sql_repository
from .postgresql.enums import *
from .postgresql.models import *

debug_mode = Jsondb.config.debug_mode
SQL_connection = Jsondb.config.SQL_connection

def create_sqldb(connect_name: str | None) -> SQLRepository:
    if connect_name:
        SQLsettings_obj = getattr(Jsondb.config, connect_name)
        SQLsettings = SQLsettings_obj.model_dump() if hasattr(SQLsettings_obj, "model_dump") else SQLsettings_obj
    else:
        SQLsettings = None

    if SQLsettings is not None and not isinstance(SQLsettings, dict):
        log.warning("Invalid SQL settings type for key '%s': %s", connect_name, type(SQLsettings).__name__)
        SQLsettings = None

    if SQLsettings is not None:
        try:
            from sqlalchemy.engine import URL

            required_keys = {"user", "password", "host", "port", "database"}
            if not required_keys.issubset(SQLsettings):
                missing_keys = required_keys - set(SQLsettings.keys())
                raise KeyError(f"Missing SQL settings keys: {sorted(missing_keys)}")

            connection_url = URL.create(
                drivername="postgresql",
                username=SQLsettings["user"],
                password=SQLsettings["password"],
                host=SQLsettings["host"],
                port=SQLsettings["port"],
                database=SQLsettings["database"],
            )
            sqlrepository = create_sql_repository(connection_url)
            name = sqlrepository.engine.dialect.name
            version = sqlrepository.engine.dialect.server_version_info
            log.info(f'>> SQL connect: online ({name}, {version}, {SQLsettings["user"]} in {SQLsettings["host"]}) <<')
        except Exception as e:
            sqlrepository = None
            log.exception(">> SQL connect: offline <<", exc_info=e)
    else:
        sqlrepository = None
        log.info(">> SQL connect: off <<")

    return sqlrepository  # pyright: ignore[reportReturnType]


sqldb = create_sqldb(SQL_connection)

Mongedb_connection = Jsondb.config.Mongedb_connection
def create_mongedb(should_connect) -> MongoDB:
    if should_connect:
        url = Jsondb.get_token("mongodb_url")
        mongedb = MongoDB(url)
        log.info(">> MongoDB connect: on <<")
    else:
        mongedb = None
    return mongedb # type: ignore

mongedb = create_mongedb(Mongedb_connection)

__all__ = [
    "sqldb",
]
