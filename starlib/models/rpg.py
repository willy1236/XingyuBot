import random
from typing import TYPE_CHECKING

import discord
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, Text

from ..base import ListObject
from ..types import EquipmentSolt, ItemCategory, ShopItemMode
from ..utils import BotEmbed
from .mysql import Field, Relationship, SQLModel
from .sqlSchema import RPGSchema


class RPGEquipmentSolt(RPGSchema, table=True):
    __tablename__ = "id_equipment_solt"

    solt_id: int = Field(primary_key=True)
    solt_name: str

class RPGEquipmentTemplate(RPGSchema, table=True):
    __tablename__ = "id_equipment"

    equipment_id: int = Field(primary_key=True)
    slot_id: int = Field(foreign_key="stardb_rpg.id_equipment_solt.solt_id")
    name: str
    price: int = Field(default=0)
    initial_maxhp: int = Field(default=0)
    initial_atk: int = Field(default=0)
    initial_pdef: int = Field(default=0)
    initial_hrt: int = Field(default=0)
    initial_dex: int = Field(default=0)

    equipments: list["RPGEquipment"] = Relationship(back_populates="template")

class RPGItemTemplate(RPGSchema, table=True):
    __tablename__ = "id_item"

    id: int = Field(primary_key=True)
    category_id: int = Field(default=1)
    name: str

    items: list["RPGPlayerItem"] = Relationship(back_populates="template")
    dungeon_treasures: list["RPGDungeonTreasureInfo"] = Relationship(back_populates="item")


class MonsterInBattle(RPGSchema, table=False):
    """在戰鬥前複製Monster的資料以確保資料庫內容不會被更動"""

    id: int
    name: str
    hp: int
    atk: int
    pdef: int
    hrt: int
    dex: int


class Monster(RPGSchema, table=True):
    __tablename__ = "id_monster"

    id: int = Field(primary_key=True)
    name: str
    hp: int = Field(default=0)
    atk: int = Field(default=0)
    pdef: int = Field(default=0)
    hrt: int = Field(default=0)
    dex: int = Field(default=0)
    drop_money: int = Field(default=0)

    in_dungeon: list["RPGDungeonMonsterInfo"] = Relationship(back_populates="monster")
    equipmen_drops: list["MonsterEquipmentDrop"] = Relationship(back_populates="monster")
    item_drops: list["MonsterItemDrop"] = Relationship(back_populates="monster")

    def create_monster(self):
        return MonsterInBattle(id=self.id, name=self.name, hp=self.hp, atk=self.atk, pdef=self.pdef, hrt=self.hrt, dex=self.dex)


class MonsterEquipmentDrop(RPGSchema, table=True):
    __tablename__ = "id_monster_equipment_drop"

    monster_id: int = Field(primary_key=True, foreign_key="stardb_rpg.id_monster.id")
    equipment_id: int = Field(primary_key=True, foreign_key="stardb_rpg.id_equipment.equipment_id")
    drop_probability: int = Field(default=0)

    monster: Monster = Relationship(back_populates="equipmen_drops")


class MonsterItemDrop(RPGSchema, table=True):
    __tablename__ = "id_monster_item_drop"

    monster_id: int = Field(primary_key=True, foreign_key="stardb_rpg.id_monster.id")
    item_id: int = Field(primary_key=True, foreign_key="stardb_rpg.id_item.id")
    drop_probability: int = Field(default=0)
    drop_count: int = Field(default=1)

    monster: Monster = Relationship(back_populates="item_drops")


class RPGDungeon(RPGSchema, table=True):
    __tablename__ = "id_dungeon"

    id: int = Field(primary_key=True)
    name: str
    description: str | None

    monsters: list["RPGDungeonMonsterInfo"] = Relationship(back_populates="dungeon")
    treasures: list["RPGDungeonTreasureInfo"] = Relationship(back_populates="dungeon")


class RPGDungeonMonsterInfo(RPGSchema, table=True):
    __tablename__ = "id_dungeon_monster_info"

    dungeon_id: int = Field(primary_key=True, foreign_key="stardb_rpg.id_dungeon.id")
    monster_id: int = Field(primary_key=True, foreign_key="stardb_rpg.id_monster.id")
    weight: int = Field(default=1)

    dungeon: RPGDungeon = Relationship(back_populates="monsters")
    monster: Monster = Relationship(back_populates="in_dungeon")


class RPGDungeonTreasureInfo(RPGSchema, table=True):
    __tablename__ = "id_dungeon_treasure_info"

    dungeon_id: int = Field(primary_key=True, foreign_key="stardb_rpg.id_dungeon.id")
    item_id: int = Field(primary_key=True, foreign_key="stardb_rpg.id_item.id")
    weight: int = Field(default=1)
    min_drop: int = Field(default=1)
    max_drop: int = Field(default=1)

    dungeon: RPGDungeon = Relationship(back_populates="treasures")
    item: RPGItemTemplate = Relationship(back_populates="dungeon_treasures")


class RPGUser(RPGSchema, table=True):
    """
    hp:生命 atk:攻擊 def(df):防禦\n
    DEX=Dexterity敏捷\n
    STR=Strength力量\n
    INT=Intelligence智力\n
    LUK=Lucky幸運\n
    HRT=Hit rate命中率
    """

    __tablename__ = "rpg_user"

    discord_id: int = Field(sa_column=Column(BigInteger, primary_key=True, autoincrement=False))
    hp: int = Field(default=10)
    maxhp: int = Field(default=10)
    atk: int = Field(default=1)
    pdef: int = Field(default=0)
    hrt: int = Field(default=60)
    dex: int = Field(default=0)

    equipments: list["RPGEquipment"] = Relationship(back_populates="owner")
    items: list["RPGPlayerItem"] = Relationship(back_populates="user")

    def embed(self, user_dc: discord.User):
        embed = BotEmbed.general(name=user_dc.name, icon_url=user_dc.avatar.url if user_dc.avatar else None)
        embed.add_field(name="生命/最大生命", value=f"{self.hp} / {self.maxhp}")
        embed.add_field(name="攻擊力", value=self.atk)
        embed.add_field(name="物理防禦力", value=self.pdef)
        embed.add_field(name="命中率", value=f"{self.hrt}%")
        embed.add_field(name="敏捷", value=self.dex)
        return embed

    def change_hp(self, value: int):
        self.hp += value
        if self.hp > self.maxhp:
            self.hp = self.maxhp


class RPGEquipment(RPGSchema, table=True):
    __tablename__ = "rpg_equipment_ingame"

    equipment_uid: int = Field(sa_column=Column(Integer, primary_key=True, autoincrement=True))
    equipment_id: int = Field(foreign_key="stardb_rpg.id_equipment.equipment_id")
    customized_name: str | None
    discord_id: int | None = Field(sa_column=Column(BigInteger, ForeignKey("stardb_rpg.rpg_user.discord_id")))
    slot_id: int | None = Field(foreign_key="stardb_rpg.id_equipment_solt.solt_id")
    maxhp: int = Field(default=0)
    atk: int = Field(default=0)
    pdef: int = Field(default=0)
    hrt: int = Field(default=0)
    dex: int = Field(default=0)
    inmarket: int = Field(default=0)

    template: RPGEquipmentTemplate = Relationship(back_populates="equipments")
    owner: RPGUser = Relationship(back_populates="equipments")

    def embed(self):
        embed = BotEmbed.rpg(self.customized_name if self.customized_name else self.template.name)
        embed.add_field(name="生命", value=self.maxhp)
        embed.add_field(name="攻擊力", value=self.atk)
        embed.add_field(name="物理防禦力", value=self.pdef)
        embed.add_field(name="命中率", value=f"{self.hrt}%")
        embed.add_field(name="敏捷", value=self.dex)
        return embed


class RPGPlayerItem(RPGSchema, table=True):
    __tablename__ = "rpg_user_item_bag"

    item_id: int = Field(primary_key=True, foreign_key="stardb_rpg.id_item.id")
    discord_id: int = Field(sa_column=Column(BigInteger, ForeignKey("stardb_rpg.rpg_user.discord_id"), primary_key=True))
    amount: int = Field(default=0)

    user: RPGUser = Relationship(back_populates="items")
    template: RPGItemTemplate = Relationship(back_populates="items")


class ShopItem:
    def __init__(self, data: dict):
        super().__init__(data)
        # rpg_shop
        self.shop_item_id = data.get("shop_item_id")
        self.price = data.get("item_price")
        self.mode = ShopItemMode(data.get("item_mode"))


class RPGWorkCareer:
    def __init__(self, data):
        self.career_id = data.get("career_id")
        self.name = data.get("career_name", "無業遊民")
        self.reward_item_id = data.get("reward_item_id")
        self.reward_item_min = data.get("reward_item_min")
        self.reward_item_max = data.get("reward_item_max")


class RPGPlayerWearingEquipment:
    if TYPE_CHECKING:
        head: RPGEquipment
        body: RPGEquipment
        legging: RPGEquipment
        foot: RPGEquipment
        mainhand: RPGEquipment
        seconhand: RPGEquipment

    def __init__(self, data):
        dict = {}
        if data:
            for equip in data:
                dict[str(equip.slot.value)] = equip

        self.head = dict.get("1")
        self.body = dict.get("2")
        self.legging = dict.get("3")
        self.foot = dict.get("4")
        self.mainhand = dict.get("5")
        self.seconhand = dict.get("6")

    def desplay(self,user_dc:discord.User=None):
        embed = BotEmbed.simple(f"{user_dc.name} 角色裝備" if user_dc else "角色裝備")
        embed.add_field(name="主手",value=f"[{self.mainhand.equipment_uid}]{self.mainhand.name}" if self.mainhand else "無")
        embed.add_field(name="副手",value=f"[{self.seconhand.equipment_uid}]{self.seconhand.name}" if self.seconhand else "無")
        embed.add_field(name="頭部",value=f"[{self.head.equipment_uid}]{self.head.name}" if self.head else "無")
        embed.add_field(name="身體",value=f"[{self.body.equipment_uid}]{self.body.name}" if self.body else "無")
        embed.add_field(name="腿部",value=f"[{self.legging.equipment_uid}]{self.legging.name}" if self.legging else "無")
        embed.add_field(name="鞋子",value=f"[{self.foot.equipment_uid}]{self.foot.name}" if self.foot else "無")
        return embed


class MonsterEquipmentLoot:
    def __init__(self, data):
        super().__init__(data)
        self.monster_id = data.get("monster_id")
        self.drop_probability = data.get("drop_probability", 0)

    def drop(self):
        """return: list[物品id,數量] | None(未掉落)"""
        result = random.choices([True, False], weights=[self.drop_probability, 100 - self.drop_probability])
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


class RPGMarketItem:
    def __init__(self, data):
        super().__init__(data)
        # rpg_item_market
        self.remain_amount = data.get("remain_amount")
        self.per_price = data.get("per_price")


class RPGCity:
    def __init__(self, data):
        # rpg_cities
        self.city_id = data.get("city_id")
        self.city_name = data.get("city_name")
        self.coordinate_x = data.get("coordinate_x")
        self.coordinate_y = data.get("coordinate_y")

        # rpg_cities_statue
        self.city_occupation_value = data.get("city_occupation_value")

    def desplay(self):
        embed = BotEmbed.rpg(self.city_name)
        embed.add_field(name="座標", value=f"({self.coordinate_x},{self.coordinate_y})")
        return embed
