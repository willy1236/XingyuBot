from sqlalchemy import Identity, Integer
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass, mapped_column
from sqlmodel import SQLModel


class Base(MappedAsDataclass, DeclarativeBase):
    """subclasses will be converted to dataclasses"""

    __abstract__ = True
    __dataclass_kwargs__ = {"kw_only": True}

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
    __abstract__ = True
    __table_args__ = {"schema": "stardb_basic"}


class AlchemyBasicSchema(Base):
    __abstract__ = True
    __table_args__ = {"schema": "stardb_basic"}

class BackupSchema(BaseSchema):
    __abstract__ = True
    __table_args__ = {"schema": "stardb_backup"}


class IdbaseSchema(BaseSchema):
    __abstract__ = True
    __table_args__ = {"schema": "stardb_idbase"}


class RPGSchema(BaseSchema):
    __abstract__ = True
    __table_args__ = {"schema": "stardb_rpg"}


class TokensSchema(BaseSchema):
    __abstract__ = True
    __table_args__ = {"schema": "credentials"}

class UserSchema(BaseSchema):
    __abstract__ = True
    __table_args__ = {"schema": "stardb_user"}

class CacheSchema(BaseSchema):
    __abstract__ = True
    __table_args__ = {"schema": "stardb_cache"}

class HappycampSchema(BaseSchema):
    __abstract__ = True
    __table_args__ = {"schema": "happycamp"}

class UsersSchema(BaseSchema):
    __abstract__ = True
    __table_args__ = {"schema": "users"}

class GuildsSchema(BaseSchema):
    __abstract__ = True
    __table_args__ = {"schema": "guilds"}
