from sqlmodel import SQLModel

class DatabaseSchema(SQLModel):
    __table_args__ = {'schema': 'database'}

class BasicSchema(SQLModel):
    __table_args__ = {'schema': 'stardb_basic'}

class BackupSchema(SQLModel):
    __table_args__ = {'schema': 'stardb_backup'}

class IdbaseSchema(SQLModel):
    __table_args__ = {'schema': 'stardb_idbase'}

class LedgerSchema(SQLModel):
    __table_args__ = {'schema': 'stardb_ledger'}

class RPGSchema(SQLModel):
    __table_args__ = {'schema': 'stardb_rpg'}

class TokensSchema(SQLModel):
    __table_args__ = {'schema': 'stardb_tokens'}

class UserSchema(SQLModel):
    __table_args__ = {'schema': 'stardb_user'}