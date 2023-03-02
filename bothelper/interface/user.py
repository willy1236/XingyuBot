from bothelper.database import sqldb
from bothelper.model.user import *

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