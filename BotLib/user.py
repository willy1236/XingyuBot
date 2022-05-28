from BotLib.database import Database
from BotLib.basic import BotEmbed

class User():
    def __init__(self,userid,dcname=None):
        udata = Database().udata
        self.id = str(userid)
        self.point = Point(self.id)
        if not self.id in udata:
            udata[self.id] = {}
        self.name = udata[self.id].get('name',dcname)
        
        self.desplay = self.embed()
        return
        self.weapon = udata['weapon']

    def embed(self):
        embed = BotEmbed.simple(title=self.name)
        embed.add_field(name='Pt點數',value=self.point.pt)
        return embed

    def setup(id):
        udata = Database().udata
        udata[id] = {}
        Database().write('udata',udata)

class Point():
    def __init__(self,userid:str):
        self.jpt = Database().jpt
        self.user = str(userid) #用戶
        self.pt = self.jpt[self.user] #用戶擁有PT數
    
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
