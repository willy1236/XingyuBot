import random
from re import A
from unittest import result
from BotLib.database import Database
from BotLib.basic import BotEmbed

class User():
    '''基本用戶資料'''
    def __init__(self,userid:str,dcname=None):
        self.db = Database()
        udata = self.db.udata
        jbag = self.db.jbag
        jpet = self.db.jpet

        self.id = str(userid)
        if not self.id in udata:
            self.setup()
        
        self.point = Point(self.id)
        self.name = udata[self.id].get('name',dcname)
        self.hp = udata[self.id].get('hp',10)
        self.weapon = udata[self.id].get('weapon',None)

        self.bag = jbag.get(self.id,None)
        self.pet = jpet.get(self.id,None)
        
        self.desplay = self.embed()

    def embed(self):
        embed = BotEmbed.general(name=self.name)
        embed.add_field(name='Pt點數',value=self.point.pt)
        embed.add_field(name='生命值',value=self.hp)
        if self.pet:
            embed.add_field(name='寵物',value=self.pet['name'])
        else:
            embed.add_field(name='寵物',value='無')
        return embed

    def setup(self):
        udata = self.db.udata
        udata[self.id] = {}
        self.db.write('udata',udata)

    def get_bag(self):
        dict = {}
        pass

    def advance(self):
        udata = self.db.udata
        dict = udata[self.id].get('advance',{})
        if 'times' in dict:
            dict['times'] +=1
        else:
            dict['times'] =1

        rd = random.randint(1,100)
        if rd >=1 and rd <=70:
            result = f"第{dict['times']}次冒險\n沒事發生"
        elif rd >= 71 and rd <=100:
            attecked = 1
            self.hp_add(attecked*-1)
            result = f"第{dict['times']}次冒險\n遇到怪物:你扣了{attecked}滴 還剩下{self.hp-attecked}生命值"
        
        if dict['times'] == 10:
            del udata[self.id]['advance']
            result += '\n冒險結束'
        else:
            udata[self.id]['advance'] = dict

        if self.hp <=0:
            self.hp_set(10)
            result += '\n你在冒險中死掉了 但因為此功能還在開發 你可以直接滿血復活'
        self.db.write('udata',udata)
        return result

    def hp_add(self,amount:int):
        udata = self.db.udata
        udata[self.id]['hp'] = self.hp+amount
        self.db.write('udata',udata)

    def hp_set(self,amount:int):
        udata = self.db.udata
        udata[self.id]['hp'] = amount
        self.db.write('udata',udata)

class Point():
    '''用戶pt點數'''
    def __init__(self,userid:str):
        self.jpt = Database().jpt
        self.user = str(userid) #用戶
        if self.user not in self.jpt:
            self.setup()
        self.pt = self.jpt[self.user] #用戶擁有PT數
    
    def setup(self):
        self.jpt[self.user] = 0
        Database().write('jpt',self.jpt)

    def set(self,amount:int):
        """設定用戶PT"""
        self.jpt[self.user] = amount
        Database().write('jpt',self.jpt)
    
    def add(self,amount:int):
        """增減用戶PT"""
        self.jpt[self.user] += amount
        Database().write('jpt',self.jpt)

class Pet():
    def __init__(self):
        self.name = None
        self.species = None
        self.owner = None
        return

    def setup(user):
        jpet = Database().jpet
        jpet[user] = {
            "name": None,
            "species" : None,
            "owner": user
        }
        Database().write('jpet',jpet)

class Weapon:
    def __init__(self):
        pass

class Armor:
    def __init__(self):
        pass