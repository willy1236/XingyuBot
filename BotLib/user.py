import json
from BotLib.basic import Database
from library import find

class Counter(dict):
    def __missing__(self,key): 
        return 0

class User():
    def __init__(self,userid):
        udata = Database().udata
        self.id = str(userid)
        self.point = Point(self.id)
        self.name = udata[self.id]["name"] or find.user(userid).name
            

class Point():
    def __init__(self,userid:str):
        self.jpt = Database().jpt
        self.user = str(userid) #用戶
        self.pt = self.jpt[self.user] #用戶擁有PT數
    
    def set(self,amount:int): #設定用戶PT
        self.jpt[self.user] = amount
        Database().write(self,'jpt',self.jpt)
    
    def add(self,amount:int): #增減用戶PT
        self.jpt[self.user] += amount
        Database().write(self,'jpt',self.jpt)