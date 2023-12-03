import discord,random,asyncio
from starcord.utilities.utility import BotEmbed
from starcord.DataExtractor import sclient
from starcord.models.user import RPGUser,Monster
from starcord.types import Coins

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
                if sclient.getif_bag(player.discord_id,3,1):
                    player.hp = 10
                    sclient.set_rpguser_data(player.discord_id,'user_hp',player.hp)
                    sclient.remove_bag(player.discord_id,3,1)
                    embed.description = "使用藥水復活並繼續冒險\n"
                else:
                    await interaction.edit_original_response(content="你已陣亡 請購買復活藥水復活")
                    return

            if player.rcoin <= 0:
                #await interaction.edit_original_response(content="你的Rcoin不足 至少需要1Rcoin才能冒險\n但因為目前為開發階段 那我就送你一些Rcoin吧")
                await interaction.edit_original_response(content="你的Rcoin不足 至少需要5Rcoin才能冒險")
                #sclient.update_coins(player.id,"add",Coins.RCOIN,100)
                return
                

            sclient.update_coins(player.discord_id,"add",Coins.RCOIN,-5)

        list = [embed]
        rd = random.randint(1,100)
        
        if rd > 70 and rd <=100:
            embed.description += "遇到怪物"
            monster = sclient.get_monster(random.randint(1,2))
            embed2 = BotEmbed.simple(f"遭遇戰鬥：{monster.name}")
            list.append(embed2)
            sclient.set_userdata(player.discord_id,'rpg_activities','advance_times',times)
            view = RPGBattleView(player,monster,list)
            await interaction.edit_original_response(embeds=list,view=view)
            await view.battle(interaction)
        else:
            if rd > 0 and rd <= 50:
                embed.description += "沒事發生"
                if random.randint(1,10) <= 3:
                    hp_add = random.randint(0,3)
                    embed.description += f"，並且稍作休息後繼續冒險\n生命+{hp_add}"
                    player.hp += hp_add
                    sclient.set_rpguser_data(player.discord_id,'user_hp',player.hp)

            elif rd > 50 and rd <= 60:
                embed.description += "尋獲物品"
                item = sclient.get_rpgitem(random.randint(1,3))
                sclient.update_bag(player.discord_id,item.item_id,1)
                embed.description += f"，獲得道具 {item.name}"
            elif rd > 60 and rd <= 70:
                embed.description += "採到陷阱"
                injuried_value = random.randint(1,3)
                player.hp -= injuried_value
                embed.description += f"，受到{injuried_value}點傷害"
                if player.hp <= 0:
                    embed.description += "，你已陣亡"
                sclient.set_rpguser_data(player.discord_id,'user_hp',player.hp)
            
            if times >= 5 and random.randint(0,100) <= times*5:
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

    async def battle(self,interaction: discord.Interaction,advance_view:RPGAdvanceView=None):
        '''玩家與怪物戰鬥'''
        player = self.player
        monster = self.monster
        player_hp_reduce = 0
        battle_round = 0
        embed = self.embed_list[1]
        
        #戰鬥到一方倒下
        while monster.hp > 0 and player.hp > 0:
            text = ""
            battle_round += 1
            #造成的傷害總和
            damage_player = 0
            damage_monster = 0
            
            while not self.attck:
                await asyncio.sleep(1)

            await asyncio.sleep(0.5)

            #玩家先攻
            if self.attck == 1 and random.randint(1,100) < player.hrt:
                damage_player = player.atk
                monster.hp -= damage_player
                text += "玩家：普通攻擊 "
                #怪物被擊倒
                if monster.hp <= 0:
                    text += f"\n擊倒怪物 扣除{player_hp_reduce}滴後你還剩下 {player.hp} HP"
                    # if "loot" in self.data:
                    #     loot = random.choices(self.data["loot"][0],weights=self.data["loot"][1],k=self.data["loot"][2])
                    #     player.add_bag(loot)
                    #     text += f"\n獲得道具！"
                    sclient.update_coins(player.discord_id,"add",Coins.RCOIN,monster.drop_money)
                    text += f"\nRcoin +{monster.drop_money}"
            else:
                text += "玩家：未命中 "
            
            #怪物後攻
            if monster.hp > 0:
                if random.randint(1,100) < monster.hrt:
                    damage_monster = monster.atk
                    player.hp -= damage_monster
                    player_hp_reduce += damage_monster
                    text += "怪物：普通攻擊"
                else:
                    text += "怪物：未命中"

                if damage_player == 0:
                    damage_player = "未命中"
                if damage_monster == 0:
                    damage_monster = "未命中"
                text += f"\n剩餘HP： 怪物{monster.hp}(-{damage_player}) 玩家{player.hp}(-{damage_monster})\n"
                
                #玩家被擊倒
                if player.hp <= 0:
                    text += "被怪物擊倒\n"
                    sclient.set_userdata(player.discord_id,'rpg_activities','advance_times',0)
                    # if sclient.getif_bag(player.discord_id,3,1):
                    #     player.hp = 10
                    #     sclient.update_bag(player.discord_id,3,-1)
                    #     text += '你在冒險中死掉了，自動使用復活藥水重生\n'
                    # else:
                    #     text += '你在冒險中死掉了，請購買復活藥水重生\n'

            embed.description = f"第{battle_round}回合\n{text}"
            self.enable_all_items()
            if monster.hp <= 0 or player.hp <= 0:
                #結束儲存資料
                sclient.set_rpguser_data(player.discord_id,'user_hp',player.hp)
                await interaction.edit_original_response(embeds=self.embed_list,view=RPGAdvanceView(player.discord_id))
                return
            else:
                await interaction.edit_original_response(embeds=self.embed_list,view=self)
            self.attck = None


    @discord.ui.button(label="普通攻擊",style=discord.ButtonStyle.green)
    async def button_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user.id == self.player.discord_id:
            self.attck = 1
            self.disable_all_items()
            await interaction.response.edit_message(view=self)