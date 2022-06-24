from BotLib.database import Database
from BotLib.basic import BotEmbed

class User():
    '''基本用戶資料'''
    def __init__(self,userid:str,dcname=None):
        udata = Database().udata
        self.id = str(userid)
        if not self.id in udata:
            self.setup()
        
        self.point = Point(self.id)
        self.name = udata[self.id].get('name',dcname)
        self.hp = udata[self.id].get('hp',None)

        self.desplay = self.embed()
        return
        self.weapon = udata['weapon']

    def embed(self):
        embed = BotEmbed.simple(title=self.name)
        embed.add_field(name='Pt點數',value=self.point.pt)
        return embed

    def setup(self):
        udata = Database().udata
        udata[self.id] = {}
        Database().write('udata',udata)

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

class pet():
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