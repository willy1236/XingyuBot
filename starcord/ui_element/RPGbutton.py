import discord,random,asyncio
from starcord.utility import BotEmbed
from starcord.database import sqldb
from starcord.clients.user import UserClient,RPGUser,Monster

class RPGbutton1(discord.ui.View):
    def __init__(self,userid):
        super().__init__()
        self.userid = str(userid)

    @discord.ui.button(label="進行冒險",style=discord.ButtonStyle.green)
    async def button_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        button.disabled = True
        await interaction.response.edit_message(view=self)
        button.disabled = False
        if str(interaction.user.id) == self.userid:
            user = UserClient.get_rpguser(self.userid)
            result = await self.advance(user,interaction)
        else:
            await interaction.edit_original_response(content="請不要點選其他人的按鈕",view=self)
            #await interaction.response.send_message(content=result, ephemeral=False)

    async def advance(self,player:RPGUser,interaction: discord.Interaction):
        '''進行冒險'''
        data = sqldb.get_advance(player.id)
        times = data.get('advance_times',0) + 1
        
        if times == 1:
            if player.rcoin <= 0:
                await interaction.edit_original_response(content="你的Rcoin不足 至少需要1Rcoin才能冒險\n但因為目前為開發階段 那我就送你一些Rcoin吧")
                sqldb.update_rcoin(player.id,'add',100)
                return
                

            sqldb.update_rcoin(player.id,'add',-1)

        embed = BotEmbed.simple()
        list = [embed]
        rd = random.randint(1,100)
        if rd >=1 and rd <=70:
            embed.title = f"第{times}次冒險"
            embed.description = "沒事發生"

            if times >= 5 and random.randint(0,100) <= times*5:
                sqldb.remove_userdata(player.id,'rpg_advance')
                embed.description += '，冒險結束'
            else:
                sqldb.update_userdata(player.id,'rpg_advance','advance_times',times)
            
            await interaction.edit_original_response(embeds=list,view=self)
        
        elif rd >= 71 and rd <=100:
            embed.title = f"第{times}次冒險"
            embed.description = "遇到怪物"
            monster = Monster.get_monster(random.randint(1,2))
            embed2 = BotEmbed.simple(f"遭遇戰鬥：{monster.name}")
            list.append(embed2)
            sqldb.update_userdata(player.id,'rpg_advance','advance_times',times)
            view = RPGbutton3(player,monster,list)
            await interaction.edit_original_response(embeds=list,view=view)
            await view.battle(interaction,self)
            



class RPGbutton2(discord.ui.View):
    def __init__(self,userid):
        super().__init__()
        self.userid = userid

    @discord.ui.button(label="按我進行工作",style=discord.ButtonStyle.green)
    async def button_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user.id == self.userid:
            user = UserClient.get_rpguser(str(interaction.user.id))
            result = user.work()

            await interaction.response.edit_message(content=result)

class RPGbutton3(discord.ui.View):
    def __init__(self,player:RPGUser,monster:Monster,embed_list:list[discord.Embed]):
        super().__init__()
        self.player = player
        self.monster = monster
        self.embed_list = embed_list
        self.attck = None

    async def battle(self,interaction: discord.Interaction,advance_view:discord.ui.View):
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
                    sqldb.update_rcoin(player.id, 'add',1)
                    text += f"\nRcoin+1"
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
                    player.hp = 10
                    text += '你在冒險中死掉了 但因為目前仍在開發階段 你可以直接滿血復活\n'

            embed.description = f"第{battle_round}回合\n{text}"
            self.enable_all_items()
            if monster.hp <= 0 or player.hp <= 0:
                #結束儲存資料
                print(1)
                sqldb.update_userdata(player.id, 'rpg_user','user_hp',player.hp)
                await interaction.edit_original_response(embeds=self.embed_list,view=RPGbutton1(player.id))
            else:
                await interaction.edit_original_response(embeds=self.embed_list,view=self)
            self.attck = None

        
        


    @discord.ui.button(label="普通攻擊",style=discord.ButtonStyle.green)
    async def button_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        if str(interaction.user.id) == self.player.id:
            self.attck = 1
            self.disable_all_items()
            await interaction.response.edit_message(view=self)