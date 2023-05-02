import random
from bothelper.utility import BotEmbed
from bothelper.database import sqldb

class User():
    '''基本用戶資料'''
    def __init__(self,data):
        #資料庫
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

    

    # def hp_add(self,amount:int):
    #     udata = self.__db.udata
    #     udata[self.id]['hp'] = self.hp+amount
    #     self.__db.write('udata',udata)

    # def hp_set(self,amount:int):
    #     udata = self.__db.udata
    #     udata[self.id]['hp'] = amount
    #     self.__db.write('udata',udata)

class RPGUser(User):
    '''RPG遊戲用戶'''
    def __init__(self,data):
        '''hp:生命 atk:攻擊 def:防禦\n
        DEX=Dexterity敏捷\n
        STR=Strength力量\n
        INT=Intelligence智力\n
        LUK=Lucky幸運'''
        self.id = data.get('user_id')
        self.hp = data.get('user_hp')
        self.atk = data.get('user_atk')
        self.pt = data.get('point')
        self.rcoin = data.get('rcoin')
        self.work_code = data.get('work_code')

    
    
    def advance(self) -> str:
        '''
        進行冒險
        
        Return: str（以文字輸出冒險結果）
        '''
        data = sqldb.get_advance(self.id)
        times = data.get('advance_times',0) + 1
        
        if times == 1:
            if self.rcoin <= 0:
                return "你的Rcoin不足 至少需要1Rcoin才能冒險"

            sqldb.update_rcoin(self.id,'add',-1)

        rd = random.randint(1,100)
        if rd >=1 and rd <=70:
            result = f"第{times}次冒險：沒事發生"
        elif rd >= 71 and rd <=100:
            result = f"第{times}次冒險：遇到怪物\n"
            result += Monster.get_monster(random.choice([1,2])).battle(self)
        
        if times >= 5 and random.randint(0,100) <= times*5:
            sqldb.remove_userdata(self.id,'rpg_advance')
            result += '\n冒險結束'
        else:
            sqldb.update_userdata(self.id,'rpg_advance','advance_times',times)

        return result
    
    def work(self) -> str:
        '''
        進行工作
        
        Return: str（以文字輸出工作結果）
        '''
        if not self.work_code:
            return '你還沒有選擇職業'
        
        rd = random.randint(1,100)
        if self.work_code == 1 and rd >= 50:
            sqldb.update_bag(self.id,'1',1)
            return '工作完成，獲得：麵包x1'
        else:
            return '工作完成，但沒有獲得東西'

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
    
#     def add(self,amount:int):yy
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


class Pet():
    def __init__(self,data):
        self.user_id = data['user_id']
        self.species = data['pet_species']
        self.name = data['pet_name']

    def desplay(self):
        embed = BotEmbed.general(f'寵物資訊')
        embed.add_field(name='寵物名',value=self.name)
        embed.add_field(name='寵物物種',value=self.species)
        return embed

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

class Monster:
    def __init__(self,data):        
        self.id = data.get('monster_id')
        self.name = data.get('monster_name')
        self.hp = data.get('monster_hp')
        self.atk = data.get('monster_atk')
    
    def battle(self, player:RPGUser):
        '''玩家與怪物戰鬥\n
        player:要戰鬥的玩家'''
        text = ""
        player_hp_reduce = 0
        #戰鬥到一方倒下
        while self.hp > 0 and player.hp > 0:
            #玩家先攻
            self.hp -= player.atk
            #怪物被擊倒
            if self.hp <= 0:
                text += f"擊倒怪物 扣除{player_hp_reduce}滴後你還剩下 {player.hp} HP"
                # if "loot" in self.data:
                #     loot = random.choices(self.data["loot"][0],weights=self.data["loot"][1],k=self.data["loot"][2])
                #     player.add_bag(loot)
                #     text += f"\n獲得道具！"
                sqldb.update_rcoin(player.id, 'add',1)
                text += f"\nRcoin+1"
                break
            
            #怪物後攻
            player.hp -= self.atk
            player_hp_reduce += self.atk
            #玩家被擊倒
            if player.hp <= 0:
                text += "被怪物擊倒\n"
                player.hp = 10
                text += '你在冒險中死掉了 但因為此功能還在開發 你可以直接滿血復活'
            #沒有被擊倒
            else:
                text += f"怪物剩下{self.hp}(-{player.atk})滴 你還剩下{player.hp}(-{self.atk})滴 戰鬥繼續\n"
            
        #結束儲存資料
        sqldb.update_userdata(player.id, 'rpg_user','user_hp',player.hp)
        return text
        

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