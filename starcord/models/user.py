import random,time,datetime,discord
from typing import TYPE_CHECKING
from starcord.utilities.utility import BotEmbed
from starcord.types import DBGame,Coins
from starcord.FileDatabase import Jsondb

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
        title = f'{user_dc.name} 的寵物' if user_dc else "寵物資訊"
        embed = BotEmbed.simple(title)
        embed.add_field(name='寵物名',value=self.name)
        embed.add_field(name='寵物物種',value=self.species)
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
        self.scoin = data.get('scoin') or 0
        self.point = data.get('point') or 0
        self.rcoin = data.get('rcoin') or 0
        self.guaranteed = data.get('guaranteed')
        self.max_sign_consecutive_days = data.get('max_sign_consecutive_days') or 0
        self.meatball_times = data.get('meatball_times')
        self.main_account_id = data.get('main_account')

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
            self.scoin = self.sqldb.get_scoin(self.discord_id)
        return self.scoin
    
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
    
    # def work(self) -> str:
    #     '''
    #     進行工作
        
    #     Return: str（以文字輸出工作結果）
    #     '''
    #     if not self.career_id:
    #         return '你還沒有選擇職業'
        
    #     rd = random.randint(1,100)
    #     if self.career_id == 1 and rd >= 50:
    #         sqldb.update_bag(self.id,1,1)
    #         text = '工作完成，獲得：小麥x1'
    #     elif self.career_id == 2 and rd >= 50:
    #         sqldb.update_bag(self.id,2,1)
    #         text = '工作完成，獲得：鐵礦x1'
    #     #elif self.career_id == 3 and rd >= 50:
    #     #    return '工作完成，獲得：麵包x1'
    #     #elif self.career_id == 4 and rd >= 50:
    #     #    return '工作完成，獲得：麵包x1'
    #     else:
    #         text = '工作完成，但沒有獲得東西'
    #     time.sleep(0.5)
    #     sqldb.update_userdata(self.id,"rpg_activities","work_date",datetime.date.today().isoformat())
    #     return text
        
class PartialUser(DiscordUser):
    """只含有特定資料的用戶"""
    def __init__(self,data:dict,sclient=None):
        super().__init__(data,sclient)

class GameUser(DiscordUser):
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

class WarningSheet:
    if TYPE_CHECKING:
        from starcord.DataExtractor import MySQLDatabase
        sqldb: MySQLDatabase
        warning_id: int
        discord_id: int
        moderate_user_id: int
        guild_id: int
        create_time: datetime.datetime
        moderate_type: str
        reason: str
        last_time: str
        officially_given: bool
        bot_given: bool
    
    def __init__(self,data:dict,sqldb=None):
        self.sqldb = sqldb
        self.warning_id = data.get("warning_id")
        self.discord_id = data.get("discord_id")
        self.moderate_user_id = data.get("moderate_user")
        self.guild_id = data.get("create_guild")
        self.create_time = data.get("create_time")
        self.moderate_type = data.get("moderate_type")
        self.reason = data.get("reason")
        self.last_time = data.get("last_time")
        self.bot_given = data.get("bot_given")

    @property
    def officially_given(self):
        return self.guild_id in Jsondb.jdata["debug_guild"]
    
    def display(self,bot:discord.Bot):
        user = bot.get_user(self.discord_id)
        moderate_user = bot.get_user(self.moderate_user_id)
        guild = bot.get_guild(self.guild_id)
        
        name = f'{user.name} 的警告單'
        description = f"**編號:{self.warning_id} ({self.moderate_type})**\n被警告用戶：{user.mention}\n管理員：{guild.name}/{moderate_user.mention}\n原因：{self.reason}\n時間：{self.create_time}"
        if self.officially_given:
            description += "\n機器人官方給予"
        embed = BotEmbed.general(name=name,icon_url=user.display_avatar.url,description=description)
        return embed
    
    def display_embed_field(self,bot:discord.Bot):
            moderate_user = bot.get_user(self.moderate_user_id)
            guild = bot.get_guild(self.guild_id)
            name = f"編號: {self.warning_id} ({self.moderate_type})"
            value = f"{guild.name}/{moderate_user.mention}\n{self.reason}\n{self.create_time}"
            if self.officially_given:
                value += "\n機器人官方給予"

            return name, value
    
    def remove(self):
        self.sqldb.remove_warning(self.warning_id)

class WarningList():
    def __init__(self,data:dict,sqldb=None):
        self.datalist = [WarningSheet(i,sqldb) for i in data]

    def display(self,bot:discord.Bot):
        user = bot.get_user(self.datalist[0].discord_id)
        embed = BotEmbed.general(f'{user.name} 的警告單列表（共{len(self.datalist)}筆）',user.display_avatar.url)
        for i in self.datalist:
            name, value = i.display_embed_field(bot)
            embed.add_field(name=name,value=value)
        return embed