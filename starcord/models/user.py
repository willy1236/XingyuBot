import random,time,datetime,discord
from typing import TYPE_CHECKING
from starcord.Utilities.utility import BotEmbed,ChoiceList
from starcord.types import DBGame,Coins,ActivitiesStatue
from starcord.FileDatabase import Jsondb
from .rpg import *

class RegistrationData():
    def __init__(self,data:dict):
        self.registrations_id = data.get("registrations_id") or data.get("discord_registration") or 0
        self.guild_id = data.get('guild_id')
        self.role_id = data.get('role_id')

    def __bool__(self):
        return bool(self.registrations_id)

class StarUser():
    if TYPE_CHECKING:
        user_id: str
        discord_id: int
        email: str
        drive_share_id: str

    def __init__(self,data:dict):
        self.user_id = data.get("user_id")
        self.discord_id = data.get("discord_id")
        self.email = data.get("email")
        self.drive_share_id = data.get("drive_share_id")

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
        user_dc: discord.User | None
        discord_id: int
        name: str
        point: int
        rcoin: int
        max_sign_consecutive_days: int
        meatball_times: int | None
        guaranteed: int | None
        pet: Pet | None
        main_account_id: int | None

    def __init__(self,data:dict,sqldb=None,user_dc=None):
        self.sqldb = sqldb
        self.user_dc = user_dc
        self.discord_id = data.get('discord_id')
        self.name = user_dc.name if user_dc else data.get('name')
        self._scoin = data.get('scoin')
        self._point = data.get('point')
        self._rcoin = data.get('rcoin') 
        self.guaranteed = data.get('guaranteed')
        self.max_sign_consecutive_days = data.get('max_sign_consecutive_days') or 0
        self.meatball_times = data.get('meatball_times')
        self.main_account_id = data.get('main_account')
        self.registration = RegistrationData(data)

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
    
    @property
    def mention(self):
        return f"<@{self.discord_id}>"
    
    def embed(self,bot:discord.Bot=None):
        embed = BotEmbed.general(name=self.user_dc.name if self.user_dc else self.name, icon_url=self.user_dc.avatar.url if self.user_dc.avatar else None)
        guild = None
        if bot:
            if self.main_account_id:
                main_account = bot.get_user(self.main_account_id) or self.main_account_id
                embed.description = f"{main_account.mention} 的小帳"
            
            if self.registration:
                guild = bot.get_guild(self.registration.guild_id)

        embed.add_field(name='⭐星塵',value=self.scoin)
        embed.add_field(name='PT點數',value=self.point)
        embed.add_field(name='Rcoin',value=self.rcoin)
        embed.add_field(name='連續簽到最高天數',value=self.max_sign_consecutive_days)
        if self.meatball_times:
            embed.add_field(name='貢丸次數',value=self.meatball_times)
        if guild:
            embed.add_field(name='戶籍',value=guild.name)
        return embed

    def get_alternate_account(self) -> list[int]:
        dbdata = self.sqldb.get_alternate_account(self.discord_id)
        return [data['alternate_account'] for data in dbdata]
    
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
        in_city_id: int
        activities_done: datetime.datetime

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
        self.in_city_id = data.get('in_city_id')
        self.activities_statue = ActivitiesStatue(data.get('activities_statue') or 0)
        self.activities_done = data.get('activities_done')

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
        return RPGPlayerWearingEquipment(self.sqldb.get_rpgplayer_equipment(self.discord_id,slot_id=-1))

    def desplay(self):
        embed = BotEmbed.general(name=self.user_dc.name if self.user_dc else self.name, icon_url=self.user_dc.avatar.url if self.user_dc.avatar else None)
        embed.add_field(name='生命/最大生命',value=f"{self.hp} / {self.maxhp}")
        embed.add_field(name='攻擊力',value=self.atk)
        embed.add_field(name='防禦力',value=self.df)
        embed.add_field(name='命中率',value=f"{self.hrt}%")
        embed.add_field(name='敏捷',value=self.dex)
        embed.add_field(name='Rcoin',value=self.rcoin)
        embed.add_field(name='職業',value=self.workcareer.name)
        embed.add_field(name='上次工作',value=self.last_work)
        embed.add_field(name='所在城市id',value=self.in_city_id)
        return embed
    
    def update_hp(self,value:int,save_to_db=False):
        self.hp += value
        if self.hp > self.maxhp:
            self.hp = self.maxhp
        if save_to_db:
            self.sqldb.set_rpguser_data(self.discord_id,"user_hp",self.hp)

    def update_data(self, column:str, value, table='rpg_user'):
        self.sqldb.set_userdata(self.discord_id,table,column,value)

    def update_bag(self,item_uid,amount):
        self.sqldb.update_bag(self.discord_id,item_uid,amount)
        
    def battle_with(self,enemy_id,enemy_user_dc=None):
        """
        :param enemy_id: 欲戰鬥的玩家，可直接輸入RPGUser物件
        return: 遊戲紀錄,[獲勝者, 落敗者]
        """
        enemy = enemy_id if type(enemy_id) == RPGUser else self.sqldb.get_rpguser(enemy_id,user_dc=enemy_user_dc)
        text = ""
        round = 0
        while enemy.hp > 0 and self.hp > 0:
            round += 1
            text += f"第{round}回合"
            #計算傷害
            damage_by_self = self.atk - enemy.df
            damage_by_enemy = enemy.atk - self.df

            #self先攻
            enemy.update_hp(-damage_by_self)
            text += f"\n{self.name}：{damage_by_self} / "
            
            #enemy後攻
            if enemy.hp > 0:
                self.update_hp(-damage_by_enemy)
                text += f"{enemy.name}：{damage_by_enemy}"
            else:
                text += f"{enemy.name}：未攻擊"
            
            text += "\n"
        
        #結算
        if enemy.hp > 0:
            text += f"\n{enemy.name} 倒下"
            if self.activities_statue != ActivitiesStatue.none:
                self.activities_statue = ActivitiesStatue.none
                self.update_data("activities_statue",self.activities_statue.value)
                self.sqldb.remove_city_battle(self.in_city_id,self.discord_id)
            winner = self
            loser = enemy
        elif self.hp > 0:
            text += f"\n{self.name} 倒下"
            if enemy.activities_statue != ActivitiesStatue.none:
                enemy.activities_statue = ActivitiesStatue.none
                enemy.update_data("activities_statue",enemy.activities_statue.value)
                self.sqldb.remove_city_battle(enemy.in_city_id,enemy.discord_id)
            winner = enemy
            loser = self
            

        self.update_hp(0,True)
        enemy.update_hp(0,True)

        return text, [winner,loser]
        
class CityBattlePlayer(RPGUser):
    def __init__(self, data: dict):
        super().__init__(data)
        self.city_id = data.get('city_id')
        self.in_city_statue = ActivitiesStatue(data.get('in_city_statue'))

class CityBattle(ListObject):
    if TYPE_CHECKING:
        from starcord.DataExtractor import MySQLDatabase
        sqldb: MySQLDatabase
    
    def __init__(self,data,sqldb=None):
        super().__init__()
        self.sqldb = sqldb
        self._city = None
        self._defencer = []
        self._attacker = []
        for i in data:
            self.append(CityBattlePlayer(i))

    @property
    def city(self):
        if not self._city and self[0]:
            city_id = self[0].city_id
            self._city = self.sqldb.get_city(city_id)
        return self._city

    @property
    def defencer(self) -> list[CityBattlePlayer]:
        if not self._defencer:
            self._defencer = [i for i in self if i.in_city_statue.value == ActivitiesStatue.defence_city.value]
        return self._defencer
    
    @property
    def attacker(self) -> list[CityBattlePlayer]:
        if not self._attacker:
            self._attacker = [i for i in self if i.in_city_statue.value == ActivitiesStatue.attack_city.value]
        return self._attacker

class PartialUser(DiscordUser):
    """只含有特定資料的用戶"""
    def __init__(self,data:dict,sclient=None):
        super().__init__(data,sclient)

class GameUser(DiscordUser):
    def __init__(self,data:dict):
        super().__init__(data)
    
    def get_gamedata(self,game:str):
        pass
