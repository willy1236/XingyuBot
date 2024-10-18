from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from ..types import ActivitiesStatue
from ..utilities import BotEmbed
from .rpg import *

if TYPE_CHECKING:
    from starlib.database import MySQLDatabase

@dataclass(slots=True)
class Registration():
    registrations_id: int
    guild_id: int
    role_id: int

    def __bool__(self):
        return bool(self.registrations_id)

class RPGUser():
    '''RPG遊戲用戶'''
    if TYPE_CHECKING:
        hp: int
        maxhp: int
        atk: int
        df: int
        hrt: int
        dex: int
        career_id: int
        last_work: datetime
        in_city_id: int
        activities_done: datetime

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

    def embed(self):
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
        sqldb: MySQLDatabase
    
    def __init__(self,data,sqldb=None):
        super().__init__([CityBattlePlayer(i) for i in data])
        self.sqldb = sqldb
        self._city = None
        self._defencer = []
        self._attacker = []

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
