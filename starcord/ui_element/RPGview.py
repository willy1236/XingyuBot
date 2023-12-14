from pydoc import describe
import discord,random,asyncio
from discord.components import Component
from discord.ext import pages
from starcord.utilities.utility import BotEmbed,ChoiceList
from starcord.DataExtractor import sclient
from starcord.models.user import RPGUser,Monster,RPGPlayerEquipmentBag,RPGEquipment
from starcord.types import Coins,EquipmentSolt

class RPGAdvanceView(discord.ui.View):
    def __init__(self,userid):
        super().__init__()
        self.userid = int(userid)

    @discord.ui.button(label="進行冒險",style=discord.ButtonStyle.green)
    async def button_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        button.disabled = True
        await interaction.response.edit_message(view=self)
        button.disabled = False
        if interaction.user.id == self.userid:
            user = sclient.get_rpguser(self.userid)
            result = await self.advance(user,interaction)
            if result:
                await interaction.edit_original_response(content=result,view=self)
        else:
            await interaction.edit_original_response(content="請不要點選其他人的按鈕",view=self)
            #await interaction.response.send_message(content=result, ephemeral=False)

    async def advance(self,player:RPGUser,interaction: discord.Interaction):
        '''進行冒險'''
        data = sclient.get_activities(player.discord_id)
        times = data.get('advance_times',0) + 1
        
        embed = BotEmbed.simple(f"第{times}次冒險")
        embed.description = ""
        if times == 1:
            if player.hp <= 0:
                if sclient.getif_bag(player.discord_id,13,1):
                    player.update_hp(20,True)
                    sclient.remove_bag(player.discord_id,13,1)
                    embed.description = "使用藥水復活並繼續冒險\n"
                else:
                    await interaction.edit_original_response(content="你已陣亡 請購買復活藥水復活")
                    return

        list = [embed]
        rd = random.randint(1,100)

        if rd > 70 and rd <=100:
            embed.description += "遇到怪物"
            id = random.randint(1,3)
            monster = sclient.get_monster(id)
            embed2 = BotEmbed.simple(f"遭遇戰鬥：{monster.name}")
            list.append(embed2) 
            sclient.set_userdata(player.discord_id,'rpg_activities','advance_times',times)
            view = RPGBattleView(player,monster,list)
            await interaction.edit_original_response(embeds=list,view=view)
            #await view.battle(interaction)
        else:
            if rd > 0 and rd <= 50:
                embed.description += "沒事發生"
                if random.randint(1,10) <= 3:
                    hp_add = random.randint(0,5)
                    embed.description += f"，並且稍作休息後繼續冒險\n生命+{hp_add}"
                    player.update_hp(hp_add,True)

            elif rd > 50 and rd <= 60:
                embed.description += "尋獲物品"
                item = sclient.get_rpgitem( int("1" + str(random.randint(1,3))))
                sclient.update_bag(player.discord_id,item.item_uid,1)
                embed.description += f"，獲得道具 {item.name}"
            elif rd > 60 and rd <= 70:
                embed.description += "採到陷阱"
                injuried_value = random.randint(1,3)
                player.update_hp(injuried_value,True)
                embed.description += f"，受到{injuried_value}點傷害"
                if player.hp <= 0:
                    embed.description += "，你已陣亡"
            
            if times >= 5 and random.randint(0,100) <= times*5 or player.hp <= 0:
                    sclient.set_userdata(player.discord_id,'rpg_activities','advance_times',0)
                    embed.description += '，冒險結束'
            else:
                sclient.set_userdata(player.discord_id,'rpg_activities','advance_times',times)
            
            await interaction.edit_original_response(embeds=list,view=self)
            

class RPGbutton2(discord.ui.View):
    def __init__(self,userid):
        super().__init__()
        self.userid = userid

    @discord.ui.button(label="按我進行工作",style=discord.ButtonStyle.green)
    async def button_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user.id == self.userid:
            user = sclient.get_rpguser(interaction.user.id)
            result = user.work()
            await interaction.response.edit_message(content=result)

class RPGBattleView(discord.ui.View):
    def __init__(self,player:RPGUser,monster:Monster,embed_list:list[discord.Embed]):
        super().__init__()
        self.player = player
        self.monster = monster
        self.embed_list = embed_list
        self.attck = None
        self.wait_attack = True
        self.player_hp_reduce = 0
        self.battle_round = 0
        self.battle_is_end = False

    async def player_attack_result(self,interaction: discord.Interaction):
        player = self.player
        monster = self.monster
        embed = self.embed_list[1]
        
        self.battle_round += 1
            
        #這回合命中與傷害總和
        player_hit = True
        monster_hit = True
        damage_player = 0
        damage_monster = 0
        text = ""
        #玩家先攻
        if self.attck == 1 and random.randint(1,100) < player.hrt + int((player.dex - monster.dex)/5):
            damage_player = player.atk - monster.df if player.atk - monster.df > 0 else 0
            monster.hp -= damage_player
            text += "玩家：普通攻擊 "
            #怪物被擊倒
            if monster.hp <= 0:
                #text += f"\n擊倒怪物 扣除{player_hp_reduce}滴後你還剩下 {player.hp} HP"
                text += f"\n擊倒怪物 損失 {self.player_hp_reduce} HP"

                lootlist = sclient.get_monster_loot(monster.monster_id)
                if lootlist:
                    for loot in lootlist.looting():
                        equipment_uid = sclient.add_equipment_ingame(loot.equipment_id)
                        sclient.set_rpgplayer_equipment(player.discord_id,equipment_uid)
                        text += f"\n獲得道具：{loot.name}"

                sclient.update_coins(player.discord_id,"add",Coins.RCOIN,monster.drop_money)
                text += f"\nRcoin +{monster.drop_money}"
                
                self.battle_is_end = True
        else:
            player_hit = False
            text += "玩家：未命中 "
        
        #怪物後攻
        if monster.hp > 0:
            if random.randint(1,100) < monster.hrt + int((monster.dex - player.dex)/5):
                damage_monster = monster.atk - player.df if monster.atk - player.df > 0 else 0
                player.update_hp(-damage_monster)
                self.player_hp_reduce += damage_monster
                text += "怪物：普通攻擊"
            else:
                monster_hit = False
                text += "怪物：未命中"
            
            
            #玩家被擊倒
            if player.hp <= 0:
                text += "\n被怪物擊倒"
                sclient.set_userdata(player.discord_id,'rpg_activities','advance_times',0)
                self.battle_is_end = True
        
        if not player_hit:
            damage_player = "未命中"
        if not monster_hit:
            damage_monster = "未命中"
        text += f"\n剩餘HP： 怪物{monster.hp}(-{damage_player}) / 玩家{player.hp}(-{damage_monster})"
        
        embed.description = f"第{self.battle_round}回合\n{text}"
        self.enable_all_items()

        if self.battle_is_end:
            await self.end_battle(interaction)
        else:
            await interaction.edit_original_response(embeds=self.embed_list,view=self)
            self.wait_attack = True

    async def end_battle(self,interaction: discord.Interaction):
        self.player.update_hp(0,True)
        await interaction.edit_original_response(embeds=self.embed_list,view=RPGAdvanceView(self.player.discord_id))

    @discord.ui.button(label="普通攻擊",style=discord.ButtonStyle.green)
    async def button2_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user.id == self.player.discord_id and self.wait_attack:
            self.wait_attack = False
            self.attck = 1
            self.disable_all_items()
            await interaction.response.edit_message(view=self)
            
            await self.player_attack_result(interaction)

    @discord.ui.button(label="撤離戰鬥",style=discord.ButtonStyle.red)
    async def button_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user.id == self.player.discord_id:
            embed = self.embed_list[1]
            rd = random.randint(0,int(self.player.maxhp / 10 * 3))
            self.player.update_hp(-rd)

            embed.description = f"逃避雖然可恥但有用\n你選擇撤離戰鬥，在過程中你受到 {rd} hp傷害"
            await interaction.response.edit_message(view=self)
            await self.end_battle(interaction)

class RPGEquipmentBagView(discord.ui.View):
    def __init__(self,bag:RPGPlayerEquipmentBag,user_dc:discord.User):
        super().__init__()
        self.bag = bag
        self.user_dc = user_dc
        self.paginator:pages.Paginator = None
        self.now_page_item = -1
        self.item_per_page = 10

    @property
    def now_item(self) -> RPGEquipment:
        return self.bag[self.paginator.current_page * self.item_per_page + self.now_page_item]

    def refresh_item_page(self):
        page = []
        
        for i in range(int(len(self.bag)/self.item_per_page) + 1):
            page.append(BotEmbed.rpg(f'{self.user_dc.name}的裝備包包'," "))
            
            text_list = []
            for j in range(i*self.item_per_page,(i + 1)*self.item_per_page):
                try:
                    item:RPGEquipment = self.bag[j]
                except IndexError:
                    break
                name = f"{item.customized_name}({item.name})" if item.customized_name else item.name
                text_list.append(f"[{item.equipment_uid}] {name}")
            page[i].description = "\n".join(text_list)

        if self.paginator:
            self.paginator.pages = page
        return page

    def now_item_embed(self):
        item = self.now_item
        description = f"uid/id：{item.equipment_uid}/{item.item_id}\n價格：{item.price}"
        if item.slot.value != 0:
            description +=f"\n裝備位置：{ChoiceList.get_tw(str(item.slot.value),'rpgequipment_solt')}"
        description +=f"\n最大生命（MaxHP）：{item.maxhp}\n攻擊（ATK）：{item.atk}\n防禦（DEF）：{item.df}\n命中（HRT）：{item.hrt}%\n敏捷（DEX）：{item.dex}"
        embed = BotEmbed.rpg(item.customized_name if item.customized_name else item.name,description)
        return embed
    
    @discord.ui.button(label="上個裝備",style=discord.ButtonStyle.primary)
    async def button_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.now_page_item -= 1
        if self.now_page_item <= -1:
            self.now_page_item = 9
        if self.paginator.current_page * 10 + self.now_page_item > len(self.bag):
            self.now_page_item = (len(self.bag) -1) % self.item_per_page

        embed = self.now_item_embed()
        await interaction.response.edit_message(embeds=[self.paginator.pages[self.paginator.current_page],embed])

    @discord.ui.button(label="售出裝備",style=discord.ButtonStyle.danger)
    async def button3_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user.id == self.user_dc.id and self.now_item:
            sclient.sell_rpgplayer_equipment(self.user_dc.id,self.now_item.equipment_uid)
            sclient.update_coins(self.user_dc.id,"add",Coins.RCOIN,self.now_item.price)
            
            del self.bag[self.paginator.current_page * self.item_per_page + self.now_page_item]
            self.refresh_item_page()
            await interaction.response.edit_message(content=f"已售出 {self.now_item.name} 並獲得 {self.now_item.price} Rcoin",embeds=[self.paginator.pages[self.paginator.current_page]])

    @discord.ui.button(label="批量售出",style=discord.ButtonStyle.danger)
    async def button4_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user.id == self.user_dc.id and self.now_item:
            total_price, deleted_uids = sclient.sell_rpgplayer_equipment(self.user_dc.id,equipment_id=self.now_item.item_id)
            sclient.update_coins(self.user_dc.id,"add",Coins.RCOIN,self.now_item.price)
            
            self.bag = [equip for equip in self.bag if equip.equipment_uid not in deleted_uids]

            self.refresh_item_page()
            await interaction.response.edit_message(content=f"已售出未穿著的所有 {self.now_item.name} 並獲得 {total_price} Rcoin",embeds=[self.paginator.pages[self.paginator.current_page]])

    @discord.ui.button(label="下個裝備",style=discord.ButtonStyle.primary)
    async def button2_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.now_page_item += 1
        if self.now_page_item == self.item_per_page or self.paginator.current_page * 10 + self.now_page_item > len(self.bag) -1 :
            self.now_page_item = 0

        embed = self.now_item_embed()
        await interaction.response.edit_message(embeds=[self.paginator.pages[self.paginator.current_page],embed])