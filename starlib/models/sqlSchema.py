from typing import TypeVar

from sqlalchemy import Identity, Integer
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass, mapped_column
from sqlmodel import SQLModel

OBJ = TypeVar("OBJ")

class Base(MappedAsDataclass, DeclarativeBase):
    """subclasses will be converted to dataclasses"""

    @staticmethod
    def auto_id_column(datatype=Integer):
        """返回標準的自增ID欄位設定"""
        return mapped_column(datatype, Identity(), primary_key=True, init=False)
        # return mapped_column(Integer, primary_key=True, autoincrement=True, init=False)

class BaseSchema(SQLModel):
    __table_args__: dict[str, str]

    @property
    def forigen(self):
        return f'{self.__table_args__["schema"]}.{self.__tablename__}'

class DatabaseSchema(BaseSchema):
    __table_args__ = {"schema": "database"}

class BasicSchema(BaseSchema):
    __table_args__ = {"schema": "stardb_basic"}
class AlchemyBasicSchema(Base):
    __abstract__ = True
    __table_args__ = {"schema": "stardb_basic"}

class BackupSchema(BaseSchema):
    __table_args__ = {"schema": "stardb_backup"}

class IdbaseSchema(BaseSchema):
    __table_args__ = {"schema": "stardb_idbase"}


class RPGSchema(BaseSchema):
    __table_args__ = {"schema": "stardb_rpg"}

class TokensSchema(BaseSchema):
    __table_args__ = {"schema": "stardb_tokens"}

class UserSchema(BaseSchema):
    __table_args__ = {"schema": "stardb_user"}

class CacheSchema(BaseSchema):
    __table_args__ = {"schema": "stardb_cache"}
