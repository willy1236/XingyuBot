from BotLib.database import Database
from BotLib.basic import BotEmbed

class User():
    '''基本用戶資料'''
    def __init__(self,userid:str,dcname=None):
        db = Database()
        udata = db.udata
        jbag = db.jbag
        jpet = db.jpet
        self.id = str(userid)
        if not self.id in udata:
            self.setup()
        
        self.point = Point(self.id)
        self.name = udata[self.id].get('name',dcname)
        self.hp = udata[self.id].get('hp',None)
        self.weapon = udata[self.id].get('weapon',None)

        self.bag = jbag.get(self.id,None)
        self.pet = jpet.get(self.id,None)
        
        self.desplay = self.embed()

    def embed(self):
        embed = BotEmbed.general(name=self.name)
        embed.add_field(name='Pt點數',value=self.point.pt)
        embed.add_field(name='武器',value=self.weapon)
        if self.pet:
            embed.add_field(name='寵物',value=self.pet['name'])
        else:
            embed.add_field(name='寵物',value='無')
        return embed

    def setup(self):
        udata = Database().udata
        udata[self.id] = {}
        Database().write('udata',udata)

    def get_bag(self):
        dict = {}
        pass

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