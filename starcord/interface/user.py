from starcord.database import sqldb
from starcord.model.user import *

class UserClient:
    def __init__(self):
        pass

    @staticmethod
    def get_user(user_id):
        data = sqldb.get_user(user_id)
        if data:
            return User(data)

    @staticmethod
    def get_rpguser(user_id):
        data = sqldb.get_rpguser(user_id)
        if data:
            return RPGUser(data)
    
    @staticmethod
    def get_pet(user_id):
        data = sqldb.get_user_pet(user_id)
        if data:
            return Pet(data)
        
    @staticmethod
    def get_monster(monster_id):
        data = sqldb.get_monster(monster_id)
        if data:
            return Monster(data)
        else:
            raise ValueError('monster_id is None')