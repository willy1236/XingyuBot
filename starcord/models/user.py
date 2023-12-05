import random,time,datetime,discord
from typing import TYPE_CHECKING
from starcord.utilities.utility import BotEmbed,ChoiceList
from starcord.types import DBGame,Coins
from starcord.FileDatabase import Jsondb
from .rpg import *

class Pet():
    if TYPE_CHECKING:
        discord_id: str
        species: str
        name: str
        hp: int
        food: int

    def __init__(self,data):
        self.discord_id = data['discord_id']
        self.species = data['pet_species']
        self.name = data['pet_name']
        self.food = data.get('food')

    def desplay(self,user_dc:discord.User=None):
        title = self.name
        description = f'{user_dc.name} 的寵物' if user_dc else "寵物資訊"
        embed = BotEmbed.simple(title,description)
        #embed.add_field(name='寵物名',value=self.name)
        embed.add_field(name='寵物物種',value=ChoiceList.get_tw(self.species,"pet_option"))
        embed.add_field(name='飽食度',value=self.food)
        return embed

class User:
    """基本用戶"""

class DiscordUser():
    """Discord用戶"""
    if TYPE_CHECKING:
        from starcord.DataExtractor import MySQLDatabase
        sqldb: MySQLDatabase
        user_dc: discord.User
        discord_id: int
        name: str
        point: int
        rcoin: int
        max_sign_consecutive_days: int
        meatball_times: int | None
        guaranteed: int | None
        pet: Pet | None
        main_account_id: int | None

    def __init__(self,data:dict,sqldb,user_dc=None):
        self.sqldb = sqldb
        self.user_dc = user_dc
        self.discord_id = data.get('discord_id')
        self.name = data.get('name')
        self._scoin = data.get('scoin')
        self._point = data.get('point')
        self._rcoin = data.get('rcoin') 
        self.guaranteed = data.get('guaranteed')
        self.max_sign_consecutive_days = data.get('max_sign_consecutive_days') or 0
        self.meatball_times = data.get('meatball_times')
        self.main_account_id = data.get('main_account')

    @property
    def scoin(self):
        if not self._scoin:
            self._scoin = self.sqldb.get_coin(self.discord_id) or 0
        return self._scoin
    
    @property
    def point(self):
        if not self._point:
            self._point = self.sqldb.get_coin(self.discord_id,Coins.POINT) or 0
        return self._point
    
    @property
    def rcoin(self):
        if not self._rcoin:
            self._rcoin = self.sqldb.get_coin(self.discord_id,Coins.RCOIN) or 0
        return self._rcoin
    
    def desplay(self,bot:discord.Bot=None):
        embed = BotEmbed.general(name=self.user_dc.name if self.user_dc else self.name, icon_url=self.user_dc.avatar.url if self.user_dc.avatar else discord.Embed.Empty)
        if bot and self.main_account_id:
            main_account = bot.get_user(self.main_account_id) or self.main_account_id
            embed.description = f"{main_account.mention} 的小帳"
        embed.add_field(name='星幣⭐',value=self.scoin)
        embed.add_field(name='PT點數',value=self.point)
        embed.add_field(name='Rcoin',value=self.rcoin)
        embed.add_field(name='連續簽到最高天數',value=self.max_sign_consecutive_days)
        if self.meatball_times:
            embed.add_field(name='貢丸次數',value=self.meatball_times)
        #embed.add_field(name='遊戲資料',value="/game find",inline=False)
        #embed.add_field(name='寵物',value="/pet check",inline=False)
        # embed.add_field(name='生命值',value=self.hp)
        # if self.pet.has_pet:
        #     embed.add_field(name='寵物',value=self.pet.name)
        # else:
        #     embed.add_field(name='寵物',value='無')
        return embed

    def get_pet(self):
        """等同於 UserClient.get_pet()"""
        self.pet = self.sqldb.get_pet(self.discord_id)
        return self.pet
    
    def get_game(self,game:DBGame=None):
        """等同於GameClient.get_user_game()"""
        player_data = self.sqldb.get_game_data(self.discord_id,game)
        return player_data
    
    def get_scoin(self,force_refresh=False):
        """取得星幣數
        :param force_refresh: 若是則刷新現有資料
        """
        if force_refresh or not hasattr(self,'scoin'):
            self._scoin = self.sqldb.get_coin(self.discord_id)
        return self._scoin
    
    def update_coins(self,mod,coin_type:Coins,amount:int):
        self.sqldb.update_coins(self.discord_id,mod,coin_type,amount)

    def get_alternate_account(self):
        return self.sqldb.get_alternate_account(self.discord_id)
    
    def get_main_account(self):
        return self.sqldb.get_main_account(self.discord_id)
    
    def update_data(self,table:str,column:str,value):
        self.sqldb.set_userdata(self.discord_id,table,column,value)

class RPGUser(DiscordUser):
    '''RPG遊戲用戶'''
    if TYPE_CHECKING:
        hp: int
        maxhp: int
        atk: int
        df: int
        hrt: int
        dex: int
        career_id: int
        last_work: datetime.datetime
        workcareer: RPGWorkCareer
        itembag: RPGPlayerItemBag
        equipmentbag: RPGPlayerEquipmentBag
        waring_equipment: RPGPlayerWearingEquipment

    def __init__(self,data:dict,*args,**kwargs):
        """
        hp:生命 atk:攻擊 def(df):防禦\n
        DEX=Dexterity敏捷\n
        STR=Strength力量\n
        INT=Intelligence智力\n
        LUK=Lucky幸運\n
        HRT=Hit rate命中率
        """
        super().__init__(data,*args,**kwargs)
        self.hp = data.get('user_hp')
        self.maxhp = data.get('user_maxhp') or 10
        self.atk = data.get('user_atk') or 1
        self.df = data.get('user_def') or 0
        self.hrt = data.get('user_hrt') or 60
        self.dex = data.get('user_dex') or 0
        self.career_id = data.get('career_id')
        self.last_work = data.get('last_work')
        self.workcareer = RPGWorkCareer(data)

    @property
    def itembag(self):
        dbdata = self.sqldb.get_bag(self.discord_id,with_name=True)
        if dbdata:
            return [RPGItem(i) for i in dbdata]
        else:
            return []
        #return RPGPlayerItemBag(self.sqldb.get_bag(self.discord_id),self.sqldb)

    @property
    def equipmentbag(self):
        return self.sqldb.get_equipmentbag_desplay(self.discord_id)

    @property
    def waring_equipment(self):
        return RPGPlayerWearingEquipment(self.sqldb.get_rpgplayer_waring_equipment(self.discord_id))

    def desplay(self):
        embed = BotEmbed.general(name=self.user_dc.name if self.user_dc else self.name, icon_url=self.user_dc.avatar.url if self.user_dc.avatar else discord.Embed.Empty)
        embed.add_field(name='最大生命/生命',value=f"{self.maxhp} / {self.hp}")
        embed.add_field(name='攻擊力',value=self.atk)
        embed.add_field(name='防禦力',value=self.df)
        embed.add_field(name='命中率',value=f"{self.hrt}%")
        embed.add_field(name='敏捷',value=self.dex)
        embed.add_field(name='Rcoin',value=self.rcoin)
        embed.add_field(name='職業',value=self.workcareer.name)
        embed.add_field(name='上次工作',value=self.last_work)
        return embed
    
    def update_hp(self,value:int,save_to_db=False):
        self.hp += value
        if self.hp > self.maxhp:
            self.hp = self.maxhp
        if save_to_db:
            self.sqldb.set_rpguser_data(self.discord_id,"user_hp",self.hp)
    
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
        
class PartialUser(DiscordUser):
    """只含有特定資料的用戶"""
    def __init__(self,data:dict,sclient=None):
        super().__init__(data,sclient)

class GameUser(DiscordUser):
    def __init__(self,data:dict):
        super().__init__(data)
    
    def get_gamedata(self,game:str):
        pass
