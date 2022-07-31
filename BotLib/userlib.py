import random
from BotLib.database import Database
from BotLib.basic import BotEmbed

class User():
    '''基本用戶資料'''
    def __init__(self,userid:str,dcname=None):
        self.db = Database()
        udata = self.db.udata
        jbag = self.db.jbag

        self.id = str(userid)
        if not self.id in udata:
            self.setup()
        
        self.point = Point(self.id)
        self.name = udata[self.id].get('name',dcname)
        self.hp = udata[self.id].get('hp',10)
        self.weapon = udata[self.id].get('weapon',None)
        self.att = udata[self.id].get('att',1)

        self.bag = jbag.get(self.id,None)
        self.pet = Pet(self.id)

    def desplay(self):
        embed = BotEmbed.general(name=self.name)
        embed.add_field(name='Pt點數',value=self.point.pt)
        embed.add_field(name='生命值',value=self.hp)
        if self.pet.has_pet:
            embed.add_field(name='寵物',value=self.pet.name)
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

    def add_bag(self,items:list):
        jbag = self.db.jbag
        ubag = jbag.get(self.id,{})
        for i in items:
            if i in ubag:
                ubag[i] += 1
            else:
                ubag[i] = 1
        
        jbag[self.id] = ubag
        self.db.write('jbag',jbag)

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
            result = f"第{dict['times']}次冒險：遇到怪物\n"
            result += Monster(random.choice(["001","002"])).battle(self)
        
        if dict['times'] >= 10:
            del udata[self.id]['advance']
            result += '冒險結束'
        else:
            udata[self.id]['advance'] = dict

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
    
    def __repr__(self):
        return str(self.pt)

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
    def __init__(self,user:str):
        self.db = Database()
        self.jpet = self.db.jpet
        self.user = str(user)
        data = self.jpet.get(str(user),None)
        if data:
            self.has_pet = True
            self.name = data['name']
            self.species = data['species']
        else:
            self.has_pet = False

    @staticmethod
    def add_pet(user,name,species):
        db = Database()
        jpet = db.jpet
        jpet[user] = {
            "name": name,
            "species" : species,
        }
        db.write('jpet',jpet)
    
    def remove_pet(self):
        del self.jpet[self.owner]
        self.db.write('jpet',self.jpet)

class Monster:
    def __init__(self,name):
        self.db = Database()
        self.data = self.db.monster_basic[name]
        
        self.name = name
        self.hp = self.data["hp"]
        self.att = self.data["att"]

    def battle(self, player:User):
        text = ""
        while self.hp > 0 and player.hp > 0:
            self.hp -= player.att
            if self.hp <= 0:
                text += f"擊倒怪物 你還剩下{player.hp}滴\n"
                if "loot" in self.data:
                    loot = random.choices(self.data["loot"][0],weights=self.data["loot"][1],k=self.data["loot"][2])
                    player.add_bag(loot)
                    text += f"獲得道具！\n"
                break

            player.hp -= self.att
            player.hp_set(player.hp)
            if player.hp <= 0:
                text += "被怪物擊倒\n"
                player.hp_set(10)
                text += '你在冒險中死掉了 但因為此功能還在開發 你可以直接滿血復活\n'
            else:
                text += f"怪物剩下{self.hp}(-{player.att})滴 你還剩下{player.hp}(-{self.att})滴 戰鬥繼續\n"
        return text

class Weapon:
    def __init__(self):
        pass

class Armor:
    def __init__(self):
        pass