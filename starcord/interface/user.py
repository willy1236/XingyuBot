from starcord.database import sqldb
from starcord.model.user import *

class UserClient:
    """有關用戶調用之端口"""
    def __init__(self):
        pass

    @staticmethod
    def get_user(user_id:str):
        """取得基本用戶"""
        data = sqldb.get_user(user_id)
        if data:
            return User(data)

    @staticmethod
    def get_rpguser(user_id:str):
        """取得RPG用戶"""
        data = sqldb.get_rpguser(user_id)
        if data:
            return RPGUser(data)
    
    @staticmethod
    def get_pet(user_id:str):
        """取得寵物"""
        data = sqldb.get_user_pet(user_id)
        if data:
            return Pet(data)
        
    @staticmethod
    def get_monster(monster_id:str):
        """取得怪物"""
        data = sqldb.get_monster(monster_id)
        if data:
            return Monster(data)
        else:
            raise ValueError('monster_id not found.')