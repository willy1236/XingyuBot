from library import find
from BotLib.database import Database
from BotLib.basic import BotEmbed

class User():
    def __init__(self,userid):
        udata = Database().udata
        self.id = str(userid)
        self.point = Point(self.id)
        self.name = udata[self.id].get('name',find.user(userid).name)
        
        self.desplay = self.embed()
        pass
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
    pass