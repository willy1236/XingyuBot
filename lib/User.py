import json
from library import find

class Counter(dict):
    def __missing__(self,key): 
        return 0

class User():
    def __init__(self,userid):
        udata = json.load(open('database/user_settings/basic.json','r',encoding='utf8'))
        self.id = str(userid)
        self.point = Point(self.id)
        if udata[self.id]["name"]:
            self.name = udata[self.id]["name"]
        else:
            self.name = find.user(userid).name

class Point():
    def __init__(self,userid:str):
        jpt = Counter(json.load(open('database/point.json',mode='r',encoding='utf8')))
        self.user = str(userid) #用戶
        self.pt = jpt[self.user] #用戶擁有PT數
    
    def set(self,amount:int): #設定用戶PT
        jpt = Counter(json.load(open('database/point.json',mode='r',encoding='utf8')))
        with open('database/point.json',mode='w',encoding='utf8') as jfile:
            jpt[self.user] = amount
            json.dump(jpt,jfile,indent=4)
    
    def add(self,amount:int): #增減用戶PT
        jpt = Counter(json.load(open('database/point.json',mode='r',encoding='utf8')))
        with open('database/point.json',mode='w',encoding='utf8') as jfile:
            jpt[self.user] += amount
            json.dump(jpt,jfile,indent=4)