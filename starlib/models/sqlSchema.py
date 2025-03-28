from sqlmodel import SQLModel
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import MappedAsDataclass, DeclarativeBase, declared_attr, mapped_column
from sqlalchemy import Integer, Identity
from typing import Any, Dict, TypeVar

O = TypeVar("O")

class Base(MappedAsDataclass, DeclarativeBase):
    """subclasses will be converted to dataclasses"""

    @classmethod
    def auto_id_column(cls, datatype: O = Integer):
        """返回標準的自增ID欄位設定"""
        return mapped_column(datatype, Identity(), primary_key=True, init=False)
        # return mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
        
    # # 為所有子類別的自動遞增欄位設定 init=False
    # @classmethod
    # def __get_declarations__(cls, **kw: Any) -> Dict[str, Any]:
    #     """
    #     此方法在類別被映射為資料類別時呼叫，用於自訂資料類別欄位的行為
    #     我們在這裡為所有主鍵且自動遞增的欄位設定 init=False
    #     """
    #     # 獲取父類別的欄位宣告
    #     declarations = super().__get_declarations__(**kw)
        
    #     # 查詢所有欄位
    #     if hasattr(cls, '__table__') and not cls.__dict__.get('__abstract__', False):
    #         for column in cls.__table__.columns:
    #             # 如果欄位是主鍵且自動遞增
    #             if column.primary_key and column.autoincrement:
    #                 # 確保對應的欄位在 declarations 中且設定 init=False
    #                 field_name = column.key
    #                 if field_name in declarations:
    #                     # 取得現有的欄位設定
    #                     field_dict = declarations[field_name]
                        
    #                     # 更新 metadata 中的 init 參數為 False
    #                     if 'metadata' in field_dict:
    #                         field_dict['metadata']['init'] = False
    #                     else:
    #                         field_dict['metadata'] = {'init': False}

    #                     # 設定預設值為 None
    #                     field_dict['default'] = None
        
    #     return declarations

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