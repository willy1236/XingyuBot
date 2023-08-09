import random,datetime,time
from typing import TYPE_CHECKING
from starcord.database import sqldb
from starcord.utility import BotEmbed

class UserClient:
    """有關用戶調用之端口"""
    def __init__(self):
        pass

    @staticmethod
    def get_user(user_id:str):
        """取得基本用戶"""
        data = sqldb.get_user(user_id)
        if data:
            return User(data)

    @staticmethod
    def get_rpguser(user_id:str):
        """取得RPG用戶"""
        data = sqldb.get_rpguser(user_id)
        if data:
            return RPGUser(data)
    
    @staticmethod
    def get_pet(user_id:str):
        """取得寵物"""
        data = sqldb.get_user_pet(user_id)
        if data:
            return Pet(data)
        
    @staticmethod
    def get_monster(monster_id:str):
        """取得怪物"""
        cursor = sqldb.cursor
        cursor.execute(f'SELECT * FROM `checklist`.`rpg_monster` WHERE `monster_id` = %s;',(monster_id,))
        dbdata = cursor.fetchone()
        if dbdata:
            return Monster(dbdata)
        else:
            raise ValueError('monster_id not found.')

class WarningClient:
    """警告系統調用端口"""

class User():
    '''基本用戶'''
    if TYPE_CHECKING:
        id: int
        name: str
        point: int
        rcoin: int
        max_sign_consecutive_days: int

    def __init__(self,data:dict):
        self.id = data.get('user_id')
        self.name = data.get('name')
        self.point = data.get('point')
        self.rcoin = data.get('rcoin')
        self.max_sign_consecutive_days = data.get('max_sign_consecutive_days',0)
        
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
        embed.add_field(name='PT點數',value=self.point)
        embed.add_field(name='Rcoin',value=self.rcoin)
        embed.add_field(name='連續簽到最高天數',value=self.max_sign_consecutive_days)
        embed.add_field(name='遊戲資料',value="/game find")
        embed.add_field(name='寵物',value="/pet check",inline=False)
        # embed.add_field(name='生命值',value=self.hp)
        # if self.pet.has_pet:
        #     embed.add_field(name='寵物',value=self.pet.name)
        # else:
        #     embed.add_field(name='寵物',value='無')
        return embed

    def get_pet(self):
        """等同於 UserClient.get_pet()"""
        dbdata = UserClient.get_pet(self.id)
        return dbdata

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
    if TYPE_CHECKING:
        hp: int
        atk: int
        hrt: int
        career_id: int
    
    def __init__(self,data):
        """
        hp:生命 atk:攻擊 def:防禦\n
        DEX=Dexterity敏捷\n
        STR=Strength力量\n
        INT=Intelligence智力\n
        LUK=Lucky幸運\n
        HRT=Hit rate命中率
        """
        super().__init__(data)
        self.hp = data.get('user_hp')
        self.atk = data.get('user_atk')
        self.hrt = data.get('hrt',60)
        self.career_id = data.get('career_id')

    
    # def advance(self) -> list[discord.Embed]:
    #     '''
    #     進行冒險
        
    #     Return: list[discord.Embed]（輸出冒險結果）
    #     '''
    #     data = sqldb.get_advance(self.id)
    #     times = data.get('advance_times',0) + 1
        
    #     if times == 1:
    #         if self.rcoin <= 0:
    #             return "你的Rcoin不足 至少需要1Rcoin才能冒險"

    #         sqldb.update_rcoin(self.id,'add',-1)

    #     embed = BotEmbed.simple()
    #     list = [embed]
    #     rd = random.randint(71,100)
    #     if rd >=1 and rd <=70:
    #         embed.title = f"第{times}次冒險"
    #         embed.description = "沒事發生"
    #     elif rd >= 71 and rd <=100:
    #         embed.title = f"第{times}次冒險"
    #         embed.description = "遇到怪物"
    #         monster = Monster.get_monster(random.randint(1,2))
    #         embed2 = monster.battle(self)
    #         list.append(embed2)

    #         embed = BotEmbed.simple(f"遭遇戰鬥：{self.name}")
    #         view = RPGbutton3(self,monster,embed)
    #     if times >= 5 and random.randint(0,100) <= times*5:
    #         sqldb.remove_userdata(self.id,'rpg_activities')
    #         embed.description += '，冒險結束'
    #     else:
    #         sqldb.update_userdata(self.id,'rpg_activities','advance_times',times)

    #     return list
    
    def work(self) -> str:
        '''
        進行工作
        
        Return: str（以文字輸出工作結果）
        '''
        if not self.career_id:
            return '你還沒有選擇職業'
        
        rd = random.randint(1,100)
        if self.career_id == 1 and rd >= 50:
            sqldb.update_bag(self.id,1,1)
            text = '工作完成，獲得：小麥x1'
        elif self.career_id == 2 and rd >= 50:
            sqldb.update_bag(self.id,2,1)
            text = '工作完成，獲得：鐵礦x1'
        #elif self.career_id == 3 and rd >= 50:
        #    return '工作完成，獲得：麵包x1'
        #elif self.career_id == 4 and rd >= 50:
        #    return '工作完成，獲得：麵包x1'
        else:
            text = '工作完成，但沒有獲得東西'
        time.sleep(0.5)
        sqldb.update_userdata(self.id,"rpg_activities","work_date",datetime.date.today().isoformat())
        return text
        
class GameUser(User):
    def __init__(self,data:dict):
        super().__init__(data)
    
    def get_gamedata(self,game:str):
        pass

class Monster:
    if TYPE_CHECKING:
        id: str
        name: str
        hp: int
        atk: int
        hrt: int

    def __init__(self,data):
        self.id = data.get('monster_id')
        self.name = data.get('monster_name')
        self.hp = data.get('monster_hp')
        self.atk = data.get('monster_atk')
        self.hrt = data.get('hrt')
    
    @staticmethod
    def get_monster(monster_id:str):
        """取得怪物"""
        data = sqldb.get_monster(monster_id)
        if data:
            return Monster(data)
        else:
            raise ValueError('monster_id not found.')


    # def battle(self, player:RPGUser):
    #     '''玩家與怪物戰鬥\n
    #     player:要戰鬥的玩家'''
    #     player_hp_reduce = 0
    #     battle_round = 0
    #     embed = BotEmbed.simple(f"遭遇戰鬥：{self.name}")
    #     #戰鬥到一方倒下
    #     while self.hp > 0 and player.hp > 0:
    #         text = ""
    #         battle_round += 1
    #         #造成的傷害總和
    #         damage_player = 0
    #         damage_monster = 0
            
    #         #玩家先攻
    #         if random.randint(1,100) < player.hrt:
    #             damage_player = player.atk
    #             self.hp -= damage_player
    #             text += "玩家：普通攻擊 "
    #             #怪物被擊倒
    #             if self.hp <= 0:
    #                 text += f"\n擊倒怪物 扣除{player_hp_reduce}滴後你還剩下 {player.hp} HP"
    #                 # if "loot" in self.data:
    #                 #     loot = random.choices(self.data["loot"][0],weights=self.data["loot"][1],k=self.data["loot"][2])
    #                 #     player.add_bag(loot)
    #                 #     text += f"\n獲得道具！"
    #                 sqldb.update_rcoin(player.id, 'add',1)
    #                 text += f"\nRcoin+1"
    #         else:
    #             text += "玩家：未命中 "
            
    #         #怪物後攻
    #         if self.hp > 0:
    #             if random.randint(1,100) < self.hrt:
    #                 damage_monster = self.atk
    #                 player.hp -= damage_monster
    #                 player_hp_reduce += damage_monster
    #                 text += "怪物：普通攻擊"
    #             else:
    #                 text += "怪物：未命中"

    #             if damage_player == 0:
    #                 damage_player = "未命中"
    #             if damage_monster == 0:
    #                 damage_monster = "未命中"
    #             text += f"\n剩餘HP： 怪物{self.hp}(-{damage_player}) 玩家{player.hp}(-{damage_monster})\n"
                
    #             #玩家被擊倒
    #             if player.hp <= 0:
    #                 text += "被怪物擊倒\n"
    #                 player.hp = 10
    #                 text += '你在冒險中死掉了 但因為目前仍在開發階段 你可以直接滿血復活\n'
            
    #         embed.add_field(name=f"\n第{battle_round}回合\n",value=text,inline=False)
            
    #     #結束儲存資料
    #     sqldb.update_userdata(player.id, 'rpg_user','user_hp',player.hp)
    #     return embed
    
class Pet():
    if TYPE_CHECKING:
        user_id: str
        species: str
        name: str
        hp: int
        food: int

    def __init__(self,data):
        self.user_id = data['user_id']
        self.species = data['pet_species']
        self.name = data['pet_name']
        self.food = data.get('food')

    def desplay(self):
        embed = BotEmbed.simple()
        embed.add_field(name='寵物名',value=self.name)
        embed.add_field(name='寵物物種',value=self.species)
        embed.add_field(name='飽食度',value=self.food)
        return embed
