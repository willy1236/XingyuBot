import random
from typing import TYPE_CHECKING

import discord
from discord.ext import pages

from starlib import sqldb, Jsondb
from starlib.models.rpg import Monster, RPGEquipment, RPGPlayerItem, MonsterInBattle
from starlib.types import Coins
from starlib.utils import BotEmbed


class RPGAdvanceButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="進行冒險", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        self.view:RPGAdvanceView
        if interaction.user.id == self.view.player.discord_id:
            if not self.view.wait_attack:
                await self.view.advance(interaction)
            else:
                await interaction.edit_original_response(content="你正在戰鬥的回合中",view=self.view)
        else:
            await interaction.edit_original_response(content="請不要點選其他人的按鈕",view=self.view)

class RPGBattleNormalButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="普通攻擊", style=discord.ButtonStyle.green)

    async def callback(self, interaction: discord.Interaction):
        self.view:RPGAdvanceView
        if interaction.user.id == self.view.player.discord_id and self.view.wait_attack:
            self.view.wait_attack = False
            
            await self.view.calculate_battle(interaction, 1)
        else:
            await interaction.response.edit_message(content="你沒有要戰鬥的回合",view=self.view)

class RPGBattleGetAwayButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="逃避對戰", style=discord.ButtonStyle.red)

    async def callback(self, interaction: discord.Interaction):
        self.view:RPGAdvanceView
        if interaction.user.id == self.view.player.discord_id and self.view.wait_attack:
            self.view.wait_attack = False
            embed = self.view.embed_list[2]
            rd = random.randint(0,int(self.view.player.maxhp / 10 * 3))
            self.view.player.change_hp(-rd)

            embed.description = f"逃避雖然可恥但有用\n你選擇撤離戰鬥，在過程中你受到 {rd} hp傷害"
            if self.view.player.hp <= 0:
                embed.description = "\n最終逃跑失敗倒下了"
            self.view.update_player_embed()
            await self.view.end_battle(interaction)
        else:
            await interaction.response.edit_message(content="你沒有要戰鬥的回合")

class RPGAdvanceView(discord.ui.View):
    def __init__(self, userid, dungeon_id, user_dc:discord.Member):
        super().__init__()
        self.dungeon = sqldb.get_rpg_dungeon(dungeon_id)
        self.player = sqldb.get_user_rpg(userid)
        self.advance_times = 1
        self.embed_list:list[discord.Embed] = [self.player.embed(user_dc), None]
        self.user_dc = user_dc
        
        self.wait_attack = False
        self.battle_round = 1
        self.meet_monster:Monster = None
        self.battle_monster:MonsterInBattle = None
        self.battle_is_end = False
        
        self.advance_button = RPGAdvanceButton()
        self.battle_normal = RPGBattleNormalButton()
        self.battle_getaway = RPGBattleGetAwayButton()
        self.add_item(self.advance_button)
        self.add_item(self.battle_normal)
        self.add_item(self.battle_getaway)
        self.button_set_advance()

    def button_set_advance(self):
        self.children:list[discord.Button]
        self.children[0].disabled = False
        for item in self.children[1:3]:
            item.disabled = True

    def button_set_battle(self):
        self.children:list[discord.Button]
        self.children[0].disabled = True
        for item in self.children[1:3]:
            item.disabled = False

    def update_player_embed(self):
        self.embed_list[0] = self.player.embed(self.user_dc)

    async def update_message(self, interaction: discord.Interaction):
        if interaction.response.is_done():
            await interaction.edit_original_response(embeds=self.embed_list,view=self)
        else:
            await interaction.response.edit_message(embeds=self.embed_list,view=self)

    async def advance(self,interaction: discord.Interaction):
        '''進行冒險'''
        player = self.player
        times = self.advance_times

        embed = BotEmbed.simple(f"{self.dungeon.name}：第{times}次冒險")
        embed.description = ""
        if player.hp <= 0:
            player.hp = player.maxhp
            sqldb.merge(player)
            await interaction.edit_original_response(content="你已陣亡但已自動補血", view=self)

        self.embed_list[1] = embed
        if len(self.embed_list) > 2:
            self.embed_list.pop(2)
        rd = random.randint(1,100)

        if rd > 70 and rd <=100:
            embed.description += "遇到怪物"
            self.battle_init()
        else:
            if rd > 0 and rd <= 50:
                embed.description += "沒事發生"
                if random.randint(1,10) <= 3:
                    hp_add = random.randint(0,5)
                    embed.description += f"，並且稍作休息後繼續冒險\n生命+{hp_add}"
                    player.change_hp(hp_add)
                    sqldb.merge(player)

            elif rd > 50 and rd <= 60:
                embed.description += "尋獲物品"
                if self.dungeon.treasures:
                    treasures_weights = [t.weight for t in self.dungeon.treasures]
                    treasure = random.choices(self.dungeon.treasures, treasures_weights)[0]
                    item = sqldb.get_player_item(player.discord_id, treasure.item_id) or RPGPlayerItem(item_id=treasure.item_id, discord_id=player.discord_id)
                    get_amount = random.randint(treasure.min_drop, treasure.max_drop)
                    item.amount += get_amount
                    sqldb.merge(item)
                    embed.description += f"，獲得道具 {treasure.item.name} * {get_amount}"
                else:
                    embed.description += f"\n不知道是不是看錯了，你並沒有找到任何東西"

            elif rd > 60 and rd <= 70:
                embed.description += "踩到陷阱"
                injuried_value = random.randint(1,3)
                player.change_hp(-injuried_value)
                sqldb.merge(player)
                embed.description += f"，受到{injuried_value}點傷害"
                if player.hp <= 0:
                    embed.description += "，你已陣亡"
            self.update_player_embed()

            if times >= 5 and random.randint(0,100) <= times*5 or player.hp <= 0:
                    embed.description += '，冒險結束'
                    self.clear_items()
                    self.stop()
            else:
                self.advance_times += 1
            
        await self.update_message(interaction)

    def battle_init(self):
        self.button_set_battle()
        monsters = self.dungeon.monsters
        weight_list = [m.weight for m in monsters]
        monster_id = random.choices(monsters, weight_list)[0].monster_id
        self.meet_monster = sqldb.get_monster(monster_id)
        self.battle_monster = self.meet_monster.create_monster()

        embed2 = BotEmbed.simple(f"遭遇戰鬥：{self.meet_monster.name}")
        self.embed_list.append(embed2)
        self.battle_round = 1
        self.battle_is_end = False
        self.wait_attack = True

    async def calculate_battle(self, interaction:discord.Interaction, attack_type):
        player = self.player
        monster = self.battle_monster
        player_hp_reduce = 0
        embed = self.embed_list[2]
        
        #這回合命中與傷害總和
        player_hit = True
        monster_hit = True
        damage_player = 0
        damage_monster = 0
        text = ""
        #玩家先攻
        if attack_type == 1 and random.randint(1,100) < player.hrt + int((player.dex - monster.dex)/5):
            damage_player = player.atk - monster.pdef if player.atk - monster.pdef > 0 else 0
            monster.hp -= damage_player
            text += "玩家：普通攻擊\n"
            #怪物被擊倒
            if monster.hp <= 0:
                text += f"擊倒怪物 損失 {player_hp_reduce} HP"

                # 隨機掉落裝備
                if self.meet_monster.equipmen_drops:
                    eloot_list = []
                    for drop in self.meet_monster.equipmen_drops:
                        if random.randint(1,100) <= drop.drop_probability:
                            e = RPGEquipment(equipment_id=drop.equipment_id, discord_id=player.discord_id)
                            e.slot_id = e.template.slot_id
                            eloot_list.append(e)
                            text += f"\n獲得裝備：{e.template.name}"
                    sqldb.batch_add(eloot_list)

                # 隨機掉落道具
                if self.meet_monster.item_drops:
                    iloot_list = []
                    for drop in self.meet_monster.item_drops:
                        if random.randint(1,100) <= drop.drop_probability:
                            i = sqldb.get_player_item(player.discord_id, drop.item_id) or RPGPlayerItem(item_id=drop.item_id, discord_id=player.discord_id, amount=0)
                            drop_count = random.randint(1, drop.drop_count)
                            i.amount += drop_count
                            iloot_list.append(i)
                            text += f"\n獲得道具：{i.template.name} * {drop_count}"
                    sqldb.batch_merge(iloot_list)
                
                self.battle_is_end = True
        else:
            player_hit = False
            text += "玩家：未命中\n"
        
        #怪物後攻
        if monster.hp > 0:
            if random.randint(1,100) < monster.hrt + int((monster.dex - player.dex)/5):
                damage_monster = monster.atk - player.pdef if monster.atk - player.pdef > 0 else 0
                player.change_hp(-damage_monster)
                player_hp_reduce += damage_monster
                text += "怪物：普通攻擊"
            else:
                monster_hit = False
                text += "怪物：未命中"
            
            
            #玩家被擊倒
            if player.hp <= 0:
                text += "\n被怪物擊倒"
                player.hp = 0
                self.battle_is_end = True
        
        # 攻擊與受傷展示
        if not player_hit:
            damage_player = "未命中"
        if not monster_hit:
            damage_monster = "未命中"
        text += f"\n剩餘HP： 怪物：{monster.hp}(-{damage_player}) / 玩家：{player.hp}(-{damage_monster})"
        
        embed.description = f"**第{self.battle_round}回合**\n{text}"
        self.update_player_embed()

        if self.battle_is_end:
            await self.end_battle(interaction)
        else:
            self.button_set_battle()
            await self.update_message(interaction)
            self.battle_round += 1
            self.wait_attack = True
            
    async def end_battle(self, interaction: discord.Interaction):
        sqldb.merge(self.player)
        
        if self.player.hp > 0:
            self.button_set_advance()
            self.advance_times += 1
        else:
            self.clear_items()

        await self.update_message(interaction)

class RPGbutton2(discord.ui.View):
    def __init__(self,userid):
        super().__init__()
        self.userid = userid

    @discord.ui.button(label="按我進行工作",style=discord.ButtonStyle.green)
    async def button_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user.id == self.userid:
            user = sqldb.get_rpguser(interaction.user.id)
            result = user.work()
            await interaction.response.edit_message(content=result)

class RPGEquipmentSelect(discord.ui.Select):
    def __init__(self, bag:list[RPGEquipment]):
        self.bag = bag
        super().__init__(
            placeholder="選擇裝備",
            max_values=1,
            min_values=1,
            options=[ discord.SelectOption(label=i.customized_name if i.customized_name else i.template.name, 
                                           description=f"[{i.equipment_uid}] {i.template.name}", 
                                           value=str(i.equipment_uid)
                                           ) for i in bag]
        )

    async def callback(self, interaction: discord.Interaction):
        self.view:RPGEquipmentSelectView
        uid = int(self.values[0])
        await interaction.response.edit_message(embed=next((item for item in self.bag if item.equipment_uid == uid), None).embed())

class RPGEquipmentSelectView(discord.ui.View):
    item_per_page = 10
    def __init__(self, user_dc:discord.User):
        super().__init__()
        self.user_dc = user_dc
        self.bag = sqldb.get_player_equipments(user_dc.id)
        
        self.embeds:list[discord.Embed] = None
        self.now_page = 1
        self.selects:list[RPGEquipmentSelect] = None
        self.set_embeds_selects()

        self.select = self.selects[0]
        self.add_item(self.select)
        
    def set_embeds_selects(self):
        item_embeds = []
        selects = []
        for i in range(0 , len(self.bag), self.item_per_page):
            text_list = []
            for item in self.bag[i: i + self.item_per_page]:
                name = f"{item.customized_name}({item.template.name})" if item.customized_name else item.template.name
                text_list.append(f"[{item.equipment_uid}] {name}")
            
            embed = BotEmbed.rpg(f'{self.user_dc.name}的包包', "\n".join(text_list))
            select = RPGEquipmentSelect(self.bag[i: i + self.item_per_page])
            item_embeds.append(embed)
            selects.append(select)

        self.embeds = item_embeds
        self.selects = selects
    
    async def change_page(self,interaction: discord.Interaction):
        print(self.children)
        embed = self.embeds[self.now_page - 1]
        self.select = self.selects[self.now_page - 1]
        now_button:discord.Button = self.get_item("rpgequipment_now_page")
        now_button.label = f"{self.now_page}/{len(self.embeds)}"
        await interaction.response.edit_message(embeds=[embed], view=self)

    @discord.ui.button(label="上一頁",style=discord.ButtonStyle.primary, row=1)
    async def button_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user.id == self.user_dc.id:
            num_back = self.now_page - 1
            if num_back == 0:
                num_back = len(self.embeds)
                await self.change_page(interaction)


    @discord.ui.button(label="售出裝備",style=discord.ButtonStyle.danger, row=1)
    async def button3_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user.id == self.user_dc.id and self.now_item:
            sqldb.sell_rpgplayer_equipment(self.user_dc.id,self.now_item.equipment_uid)
            sqldb.update_coins(self.user_dc.id,"add",Coins.Rcoin,self.now_item.price)
            
            del self.bag[self.paginator.current_page * self.item_per_page + self.now_page_item]
            self.refresh_item_page()
            await interaction.response.edit_message(content=f"已售出 {self.now_item.name} 並獲得 {self.now_item.price} Rcoin",embeds=[self.paginator.pages[self.paginator.current_page]])

    @discord.ui.button(label="當前頁面",style=discord.ButtonStyle.gray, row=1, custom_id="rpgequipment_now_page")
    async def button5_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user.id == self.user_dc.id:
            await self.change_page(interaction)

    @discord.ui.button(label="批量售出",style=discord.ButtonStyle.danger, row=1)
    async def button4_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user.id == self.user_dc.id and self.now_item:
            total_price, deleted_uids = sqldb.sell_rpgplayer_equipment(self.user_dc.id,equipment_id=self.now_item.item_id)
            sqldb.update_coins(self.user_dc.id,"add",Coins.Rcoin,self.now_item.price)
            
            self.bag = [equip for equip in self.bag if equip.equipment_uid not in deleted_uids]

            self.refresh_item_page()
            await interaction.response.edit_message(content=f"已售出未穿著的所有 {self.now_item.name} 並獲得 {total_price} Rcoin",embeds=[self.paginator.pages[self.paginator.current_page]])

    @discord.ui.button(label="下一頁",style=discord.ButtonStyle.primary, row=1)
    async def button2_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user.id == self.user_dc.id:
            num_next = self.now_page + 1
            if num_next == len(self.embeds) + 1:
                num_next = 1
                await self.change_page(interaction)