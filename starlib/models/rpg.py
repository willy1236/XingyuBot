import discord,random
from typing import TYPE_CHECKING
from .BaseModel import ListObject
from ..types import ItemCategory,ShopItemMode,EquipmentSolt
from ..utilities import BotEmbed

class Monster:
    if TYPE_CHECKING:
        monster_id: int
        name: str
        hp: int
        atk: int
        df: int
        hrt: int
        dex: int

    def __init__(self,data):
        self.monster_id = data.get('monster_id')
        self.name = data.get('monster_name')
        self.hp = data.get('monster_hp')
        self.atk = data.get('monster_atk')
        self.df = data.get('monster_def')
        self.hrt = data.get('monster_hrt')
        self.dex = data.get('monster_dex')
        self.drop_money = data.get('monster_drop_money',0)

class RPGItem:
    if TYPE_CHECKING:
        item_id: int
        category: ItemCategory
        name: str
        item_uid: int
        amount: int
        star_uid: str
        discord_id: int

    def __init__(self,data):
        #rpg_item
        self.category = ItemCategory(data.get('item_category_id') or 1)
        self.item_id = data.get('item_id')
        self.name = data.get('item_name')
        self.item_uid = data.get('item_uid')
        self.star_uid = data.get('star_uid')

        #rpg_user_bag
        self.discord_id = data.get('discord_id')
        self.amount = data.get('amount')

# class RPGPlayerItem(RPGItem):
#     def __init__(self,data):
#         super().__init__(data)
        

class RPGPlayerItemBag(ListObject):
    def __init__(self,data,sqldb):
        super().__init__()
        self.sqldb = sqldb
        for i in data:
            self.append(RPGItem(i))

class ShopItem(RPGItem):
    def __init__(self,data:dict):
        super().__init__(data)
        #rpg_shop
        self.shop_item_id = data.get('shop_item_id')
        self.price = data.get('item_price')
        self.mode = ShopItemMode(data.get('item_mode'))

class RPGWorkCareer:
    def __init__(self,data):
        self.career_id = data.get('career_id')
        self.name = data.get('career_name',"無業遊民")
        self.reward_item_id = data.get('reward_item_id')
        self.reward_item_min = data.get('reward_item_min')
        self.reward_item_max = data.get('reward_item_max')

class RPGEquipment(RPGItem):
    def __init__(self,data:dict):
        super().__init__(data)
        #rpg_equipment
        self.equipment_id = data.get('equipment_id')
        self.name = data.get('equipment_name') or self.name
        self.price = data.get('equipment_price')

        self.maxhp = data.get('equipment_maxhp') or 0 + data.get("equipment_initial_maxhp") or 0
        self.atk = data.get('equipment_atk') or 0 + data.get("equipment_initial_atk") or 0
        self.df = data.get('equipment_def') or 0 + data.get("equipment_initial_def") or 0
        self.hrt = data.get('equipment_hrt') or 0 + data.get("equipment_initial_hrt") or 0
        self.dex = data.get('equipment_dex') or 0 + data.get("equipment_initial_dex") or 0

        #rpg_equipment_ingame
        self.equipment_uid = data.get('equipment_uid')
        self.customized_name = data.get('equipment_customized_name')
        self.slot = EquipmentSolt(data.get('slot_id') or 0)
        self.equipment_inmarket = bool(data.get('equipment_inmarket'))
        
        self.category = ItemCategory.equipment
        self.desplay_name = self.customized_name or self.name

# class RPGPartialEquipment(RPGItem):
#     def __init__(self,data:dict):
#         super().__init__(data)
#         self.equipment_uid = data.get('equipment_uid')
#         self.category = ItemCategory.equipment
#         self.name = data.get('equipment_name') or self.name
#         self.customized_name = data.get('equipment_customized_name')
#         self.price = data.get('equipment_price')
#         self.slot = EquipmentSolt(data.get('slot_id') or 0)

class RPGPlayerEquipmentBag(ListObject):
    def __init__(self,data,sqldb):
        super().__init__()
        self.sqldb = sqldb
        for i in data:
            self.append(RPGEquipment(i))
        
class RPGPlayerWearingEquipment:
    if TYPE_CHECKING:
        head:RPGEquipment
        body:RPGEquipment
        legging:RPGEquipment
        foot:RPGEquipment
        mainhand:RPGEquipment
        seconhand:RPGEquipment

    def __init__(self,data):
        dict = {}
        if data:
            for equip in data:
                dict[str(equip.slot.value)] = equip
        
        self.head = dict.get('1')
        self.body = dict.get('2')
        self.legging = dict.get('3')
        self.foot = dict.get('4')
        self.mainhand = dict.get('5')
        self.seconhand = dict.get('6')

    def desplay(self,user_dc:discord.User=None):
        embed = BotEmbed.simple(f"{user_dc.name} 角色裝備" if user_dc else "角色裝備")
        embed.add_field(name="主手",value=f"[{self.mainhand.equipment_uid}]{self.mainhand.name}" if self.mainhand else "無")
        embed.add_field(name="副手",value=f"[{self.seconhand.equipment_uid}]{self.seconhand.name}" if self.seconhand else "無")
        embed.add_field(name="頭部",value=f"[{self.head.equipment_uid}]{self.head.name}" if self.head else "無")
        embed.add_field(name="身體",value=f"[{self.body.equipment_uid}]{self.body.name}" if self.body else "無")
        embed.add_field(name="腿部",value=f"[{self.legging.equipment_uid}]{self.legging.name}" if self.legging else "無")
        embed.add_field(name="鞋子",value=f"[{self.foot.equipment_uid}]{self.foot.name}" if self.foot else "無")
        return embed
    
class MonsterEquipmentLoot(RPGEquipment):
    def __init__(self,data):
        super().__init__(data)
        self.monster_id = data.get('monster_id')
        self.drop_probability = data.get('drop_probability',0)

    def drop(self):
        """return: list[物品id,數量] | None(未掉落)"""
        result = random.choices([True,False],weights=[self.drop_probability,100-self.drop_probability])
        if result[0]:
            return self
        
class MonsterLootList(ListObject):
    def __init__(self,data):
        super().__init__()
        for i in data:
            self.append(MonsterEquipmentLoot(i))

    def looting(self) -> list[MonsterEquipmentLoot]:
        loot_list = []
        for loot in self:
            result = loot.drop()
            if result:
                loot_list.append(result)

        return loot_list
    
class RPGMarketItem(RPGItem):
    def __init__(self,data):
        super().__init__(data)
        #rpg_item_market
        self.remain_amount = data.get('remain_amount')
        self.per_price = data.get('per_price')

class RPGCity():
    def __init__(self,data):
        #rpg_cities
        self.city_id = data.get('city_id')
        self.city_name = data.get('city_name')
        self.coordinate_x = data.get('coordinate_x')
        self.coordinate_y = data.get('coordinate_y')
        
        #rpg_cities_statue
        self.city_occupation_value = data.get('city_occupation_value')

    def desplay(self):
        embed = BotEmbed.rpg(self.city_name)
        embed.add_field(name="座標",value=f"({self.coordinate_x},{self.coordinate_y})")
        return embed
    

