from sqlmodel import SQLModel
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import MappedAsDataclass, DeclarativeBase

class Base(MappedAsDataclass, DeclarativeBase):
    """subclasses will be converted to dataclasses"""

class BaseSchema(SQLModel):
    __table_args__:dict

    @property
    def forigen(self):
        return f'{self.__table_args__["schema"]}.{self.__tablename__}'

class DatabaseSchema(BaseSchema):
    __table_args__ = {'schema': 'database'}

class BasicSchema(BaseSchema):
    __table_args__ = {'schema': 'stardb_basic'}
class AlchemyBasicSchema(Base):
    __abstract__ = True
    __table_args__ = {'schema': 'stardb_basic'}

class BackupSchema(BaseSchema):
    __table_args__ = {'schema': 'stardb_backup'}

class IdbaseSchema(BaseSchema):
    __table_args__ = {'schema': 'stardb_idbase'}

class LedgerSchema(BaseSchema):
    __table_args__ = {'schema': 'stardb_ledger'}

class RPGSchema(BaseSchema):
    __table_args__ = {'schema': 'stardb_rpg'}

class TokensSchema(BaseSchema):
    __table_args__ = {'schema': 'stardb_tokens'}

class UserSchema(BaseSchema):
    __table_args__ = {'schema': 'stardb_user'}