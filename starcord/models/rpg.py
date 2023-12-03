import discord
from typing import TYPE_CHECKING
from .BaseModel import ListObject
from starcord.types import ItemType,ShopItemMode,EquipmentSolt
from starcord.utilities.utility import BotEmbed

class Monster:
    if TYPE_CHECKING:
        id: str
        name: str
        hp: int
        atk: int
        hrt: int

    def __init__(self,data):
        self.monster_id = data.get('monster_id')
        self.name = data.get('monster_name')
        self.hp = data.get('monster_hp')
        self.atk = data.get('monster_atk')
        self.hrt = data.get('monster_hrt')
        self.drop_money = data.get('monster_drop_money',1)

class RPGItem:
    if TYPE_CHECKING:
        item_id:int
        name:str
        amount:int
        type:ItemType

    def __init__(self,data):
        self.item_id = data.get('item_id')
        self.name = data.get('item_name')
        self.amount = data.get('amount')
        self.type = ItemType(data.get('item_type') or 1)

class ItemBag(ListObject):
    def __init__(self,data,sqldb):
        super().__init__()
        self.sqldb = sqldb
        for i in data:
            self.append(RPGItem(i))

class ShopItem():
    def __init__(self,data:dict):
        self.item_id = data.get('item_id')
        self.shop_item_id = data.get('shop_item_id')
        self.name = data.get('item_name')
        self.price = data.get('item_price')
        self.mode = ShopItemMode(data.get('item_mode'))

class RPGWorkCareer:
    def __init__(self,data):
        self.career_id = data.get('career_id')
        self.name = data.get('career_name',"無業遊民")
        self.reward_item_id = data.get('reward_item_id')
        self.reward_item_min = data.get('reward_item_min')
        self.reward_item_max = data.get('reward_item_max')

class WearingEquipment(RPGItem):
    def __init__(self,data):
        super().__init__(data)
        self.slot = EquipmentSolt(data.get('slot_id'))
        self.equipment_id = data.get('slot_id')
        self.name = data.get('equipment_name') or self.name
        
class RPGPlayerEquipment:
    if TYPE_CHECKING:
        head:WearingEquipment
        body:WearingEquipment
        legging:WearingEquipment
        foot:WearingEquipment
        mainhand:WearingEquipment
        seconhand:WearingEquipment

    def __init__(self,data):
        dict = {}
        for i in data:
            equip = WearingEquipment(i)
            dict[str(equip.slot.value)] = equip
        
        self.head = dict.get('1')
        self.body = dict.get('2')
        self.legging = dict.get('3')
        self.foot = dict.get('4')
        self.mainhand = dict.get('5')
        self.seconhand = dict.get('6')

    def desplay(self,user_dc:discord.User=None):
        embed = BotEmbed.simple(f"{user_dc.name} 角色裝備" if user_dc else "角色裝備")
        embed.add_field(name="主手",value=self.mainhand.name if self.mainhand else "無")
        embed.add_field(name="副手",value=self.seconhand.name if self.seconhand else "無")
        embed.add_field(name="頭部",value=self.head.name if self.head else "無")
        embed.add_field(name="身體",value=self.body.name if self.body else "無")
        embed.add_field(name="腿部",value=self.legging.name if self.legging else "無")
        embed.add_field(name="鞋子",value=self.foot.name if self.foot else "無")
        return embed