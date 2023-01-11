import random
from BotLib.file_database import JsonDatabase
from BotLib.basic import BotEmbed

class User():
    '''基本用戶資料'''
    def __init__(self,database,data):
        '''hp:生命 atk:攻擊 def:防禦\n
        DEX=Dexterity敏捷\n
        STR=Strength力量\n
        INT=Intelligence智力\n
        LUK=Lucky幸運'''
        #資料庫
        self.sqldb = database
        self.id = data['user_id']
        self.name = data['name']
        self.point = data['point']
        self.rcoin = data['rcoin']
        # self.__db = JsonDatabase()
        # udata = self.__db.udata
        # jbag = self.__db.jbag
        
        #初始設定
        # self.id = str(userid)
        # if not self.id in udata:
        #     self.setup()
        
        #基本資料
        # self.point = Point(self.id)
        # self.rcoin = Rcoin(self.id)
        # self.name = udata[self.id].get('name',dcname)
        # self.weapon = udata[self.id].get('weapon')
        
        #RPG數值
        # self.hp = udata[self.id].get('hp',10)
        # #if not "atk" in udata[self.id]:
        # #    self.RPG_setup()
        # self.atk = udata[self.id].get('atk',1)

        #其他相關
        # self.bag = jbag.get(self.id)
        # self.pet = Pet(self.id)


    def desplay(self):
        embed = BotEmbed.general(name=self.name)
        embed.add_field(name='Pt點數',value=self.point)
        embed.add_field(name='Rcoin',value=self.rcoin)
        # embed.add_field(name='生命值',value=self.hp)
        # if self.pet.has_pet:
        #     embed.add_field(name='寵物',value=self.pet.name)
        # else:
        #     embed.add_field(name='寵物',value='無')
        return embed

    # def setup(self):
    #     udata = self.__db.udata
    #     udata[self.id] = {}
    #     self.__db.write('udata',udata)
    
    # def RPG_setup(self):
    #     udata = self.__db.udata
    #     udata[self.id].get('atk',1)
    #     self.__db.write('udata',udata)

    # def get_bag(self):
    #     dict = {}
    #     pass

    # def add_bag(self,items:list):
    #     jbag = self.__db.jbag
    #     ubag = jbag.get(self.id,{})
    #     for i in items:
    #         if i in ubag:
    #             ubag[i] += 1
    #         else:
    #             ubag[i] = 1
        
    #     jbag[self.id] = ubag
    #     self.__db.write('jbag',jbag)

    # def advance(self):
    #     udata = self.__db.udata
    #     dict = udata[self.id].get('advance',{})
    #     if 'times' in dict:
    #         dict['times'] +=1
    #     else:
    #         if int(self.rcoin) <= 0:
    #             return "你的Rcoin不足 至少需要1Rcoin才能冒險"
    #         else:
    #             dict['times'] =1
    #             self.rcoin.add(-1)

    #     rd = random.randint(1,100)
    #     if rd >=1 and rd <=70:
    #         result = f"第{dict['times']}次冒險：沒事發生"
    #     elif rd >= 71 and rd <=100:
    #         result = f"第{dict['times']}次冒險：遇到怪物\n"
    #         result += Monster(random.choice(["001","002"])).battle(self)
        
    #     if dict['times'] >= 10:
    #         del udata[self.id]['advance']
    #         result += '\n冒險結束'
    #     else:
    #         udata[self.id]['advance'] = dict

    #     self.__db.write('udata',udata)
    #     return result

    # def hp_add(self,amount:int):
    #     udata = self.__db.udata
    #     udata[self.id]['hp'] = self.hp+amount
    #     self.__db.write('udata',udata)

    # def hp_set(self,amount:int):
    #     udata = self.__db.udata
    #     udata[self.id]['hp'] = amount
    #     self.__db.write('udata',udata)

# class Point():
#     '''用戶pt點數'''
#     def __init__(self,userid:str):
#         self.__db = JsonDatabase()
#         jpt = self.__db.jpt
#         self.user = str(userid) #用戶
#         if self.user not in jpt:
#             self.setup()
#         self.pt = jpt[self.user] #用戶擁有PT數
    
#     def __repr__(self):
#         return str(self.pt)

#     def __int__(self):
#         return self.pt

#     def setup(self):
#         jpt = self.__db.jpt
#         jpt[self.user] = 0
#         self.__db.write('jpt',jpt)

#     def set(self,amount:int):
#         """設定用戶PT"""
#         jpt = self.__db.jpt
#         jpt[self.user] = amount
#         self.__db.write('jpt',jpt)
    
#     def add(self,amount:int):
#         """增減用戶PT"""
#         jpt = self.__db.jpt
#         jpt[self.user] += amount
#         self.__db.write('jpt',jpt)
    
# class Rcoin:
#     def __init__(self,userid:str):
#         self.__db = JsonDatabase()
#         jRcoin = self.__db.jRcoin
#         self.user = str(userid)
#         if self.user not in jRcoin:
#             self.setup()
#         self.rcoin = jRcoin[self.user]

#     def __repr__(self):
#         return str(self.rcoin)

#     def __int__(self):
#         return self.rcoin

#     def setup(self):
#         jRcoin = self.__db.jRcoin
#         jRcoin[self.user] = 0
#         self.__db.write('jRcoin',jRcoin)

#     def set(self,amount:int):
#         """設定用戶Rcoin"""
#         jRcoin = self.__db.jRcoin
#         jRcoin[self.user] = amount
#         self.__db.write('jRcoin',jRcoin)
    
#     def add(self,amount:int):
#         """增減用戶Rcoin"""
#         jRcoin = self.__db.jRcoin
#         jRcoin[self.user] += amount
#         self.__db.write('jRcoin',jRcoin)


# class Pet():
#     def __init__(self,user:str):
#         self.__db = JsonDatabase()
#         jpet = self.__db.jpet
#         self.user = str(user)
#         data = jpet.get(self.user)
#         if data:
#             self.has_pet = True
#             self.name = data['name']
#             self.species = data['species']
#         else:
#             self.has_pet = False

#     def add_pet(self,name,species):
#         jpet = self.__db.jpet
#         #ts = translate
#         ts = {
#             'shark':'鯊魚',
#             'dog':'狗',
#             'cat':'貓',
#             'fox':'狐狸',
#             'wolf':'狼',
#             'rabbit':'兔子'
#         }
#         if species in ts:
#             dict = {
#                 "name": name,
#                 "species" : species,
#             }
#             jpet[self.user] = dict
#             self.__db.write('jpet',jpet)

#             list = [name,ts.get(species,species)]
#             return list
#         else:
#             raise ValueError('Invalid species')
    
#     def remove_pet(self):
#         jpet = self.__db.jpet
#         del jpet[self.user]
#         self.__db.write('jpet',jpet)

# class Monster:
#     def __init__(self,name):
#         self.__db = JsonDatabase()
#         self.data = self.__db.monster_basic[name]
        
#         self.name = name
#         self.hp = self.data["hp"]
#         self.atk = self.data["atk"]

#     def battle(self, player:User):
#         '''玩家與怪物戰鬥\n
#         player:要戰鬥的玩家'''
#         text = ""
#         #戰鬥到一方倒下
#         while self.hp > 0 and player.hp > 0:
#             #玩家先攻
#             self.hp -= player.atk
#             #怪物被擊倒
#             if self.hp <= 0:
#                 text += f"擊倒怪物 你還剩下{player.hp}滴"
#                 if "loot" in self.data:
#                     loot = random.choices(self.data["loot"][0],weights=self.data["loot"][1],k=self.data["loot"][2])
#                     player.add_bag(loot)
#                     text += f"\n獲得道具！"
#                 player.rcoin.add(1)
#                 text += f"\nRcoin+1"
#                 break
            
#             #怪物後攻
#             player.hp -= self.atk
#             player.hp_set(player.hp)
#             #玩家被擊倒
#             if player.hp <= 0:
#                 text += "被怪物擊倒\n"
#                 player.hp_set(10)
#                 text += '你在冒險中死掉了 但因為此功能還在開發 你可以直接滿血復活'
#             #沒有被擊倒
#             else:
#                 text += f"怪物剩下{self.hp}(-{player.atk})滴 你還剩下{player.hp}(-{self.atk})滴 戰鬥繼續\n"
#         return text

# class Weapon:
#     def __init__(self):
#         self.name = None
#         self.id = None
#         self.atk = None

# class Armor:
#     def __init__(self):
#         pass

# class Item():
#     pass