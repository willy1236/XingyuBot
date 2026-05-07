"""
### 模組：資料庫
處理資料庫連線與操作。
"""

from starlib.settings import get_settings
from starlib.utils import log

from .postgresql.client import SQLRepository, create_sql_repository
from .postgresql.enums import *
from .postgresql.models import *


def create_sqldb() -> SQLRepository:
    try:
        from sqlalchemy.engine import URL

        settings = get_settings()

        connection_url = URL.create(
            drivername="postgresql",
            username=settings.DB_USER,
            password=settings.DB_PASSWORD,
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            database=settings.DB_NAME,
        )
        sqlrepository = create_sql_repository(connection_url)
        name = sqlrepository.engine.dialect.name
        version = sqlrepository.engine.dialect.server_version_info
        log.info(f">> SQL connect: online ({name}, {version}, {settings.DB_USER} in {settings.DB_HOST}) <<")
    except Exception as e:
        sqlrepository = None
        log.exception(">> SQL connect: offline <<", exc_info=e)

    return sqlrepository  # pyright: ignore[reportReturnType]


# sqldb = create_sqldb()

__all__ = [
    # "sqldb",
]
