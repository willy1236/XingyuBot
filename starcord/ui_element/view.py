import discord,datetime,matplotlib,io
from typing import TYPE_CHECKING
from starcord.utilities.utility import BotEmbed

class PollOptionButton(discord.ui.Button):
    def __init__(self,label,poll_id,option_id,custom_id):
        super().__init__(label=label,custom_id=custom_id)
        self.poll_id = poll_id
        self.option_id = option_id
    
    async def callback(self,interaction):
        view:PollView = self.view
        view.sqldb.add_user_poll(self.poll_id,interaction.user.id,self.option_id,datetime.datetime.now())
        await interaction.response.send_message(f"{interaction.user.mention} 已投票給 {self.label}",ephemeral=True)
    
class PollEndButton(discord.ui.Button):
    def __init__(self,poll_id,created_id):
        super().__init__(label="結算投票",custom_id=f"end_poll_{poll_id}",style=discord.ButtonStyle.danger)
        self.poll_id = poll_id
        self.created_id = created_id

    async def callback(self,interaction):
        if interaction.user.id == self.created_id:
            view:PollView = self.view
            view.disable_all_items()
            view.sqldb.update_poll(self.poll_id,"is_on",0)
            
            polldata = view.sqldb.get_poll(self.poll_id)
            dbdata = view.sqldb.get_poll_vote_count(self.poll_id,view.alternate_account_can_vote)
            options_data = view.sqldb.get_poll_options(self.poll_id)

            if view.show_name:
                user_vote_data = view.sqldb.get_users_poll(self.poll_id,view.alternate_account_can_vote)
                user_vote_list = {}
                for i in range(1,len(options_data) + 1):
                    user_vote_list[str(i)] = [] 

                for i in user_vote_data:
                    discord_id = i["discord_id"]
                    vote_option = i["vote_option"]
                    user = interaction.guild.get_member(discord_id)
                    username = user.mention if user else discord_id
                    user_vote_list[str(vote_option)].append(username)

            text = ""
            labels = []
            sizes = []
            for option in options_data:
                name = option['option_name']
                id = option['option_id']
                count = dbdata.get(str(id),0)
                text += f"{name}： {count}票\n"

                if view.show_name:
                    text += ",".join(user_vote_list[str(id)]) + "\n"

                if count > 0:
                    labels.append(name)
                    sizes.append(count)

            import matplotlib.pyplot as plt
            fig, ax = plt.subplots()
            #圖表製作
            def data_string(s,d):
                t = int(round(s/100.*sum(d)))     # 透過百分比反推原本的數值
                return f'{t}\n（{s:.1f}%）'

            # 字形
            matplotlib.rc('font', family='Microsoft JhengHei')
            matplotlib.rcParams["font.sans-serif"] = ["Microsoft JhengHei"]

            # 設置顏色
            colors = ['gold', 'yellowgreen', 'lightcoral', 'lightskyblue']

            # 設置圓餅圖的突出顯示
            #explode = (0.1, 0, 0, 0)  # 將第一塊突出顯示
        
            # 繪製圓餅圖
            ax.pie(sizes, labels=labels, colors=colors, autopct=lambda i: data_string(i,sizes), shadow=False, startangle=140)
            #plt.pie()

            # 添加標題
            ax.set_title(polldata['title'])
            #plt.title()

            image_buffer = io.BytesIO()
            plt.savefig(image_buffer, format='png', dpi=200, bbox_inches='tight')
            image_buffer.seek(0)

            embed = BotEmbed.simple(polldata["title"],description=f'投票ID：{self.poll_id}\n{text}')
            await interaction.response.edit_message(embed=embed,view=view,file=discord.File(image_buffer,filename="pie.png"))
        else:
            await interaction.response.send_message(f"錯誤：只有投票發起人才能結算",ephemeral=True)
            
class PollResultButton(discord.ui.Button):
    def __init__(self,poll_id):
        super().__init__(label="查看結果",custom_id=f"poll_result_{poll_id}",style=discord.ButtonStyle.primary)
        self.poll_id = poll_id

    async def callback(self,interaction):
        view:PollView = self.view    
        if not view.results_only_initiator:
            dbdata = view.sqldb.get_poll_vote_count(self.poll_id, view.alternate_account_can_vote)
            options_data = view.sqldb.get_poll_options(self.poll_id)

            if view.show_name:
                user_vote_data = view.sqldb.get_users_poll(self.poll_id,view.alternate_account_can_vote)
                user_vote_list = {}
                for i in range(1,len(options_data) + 1):
                    user_vote_list[str(i)] = [] 

                for i in user_vote_data:
                    discord_id = i["discord_id"]
                    vote_option = i["vote_option"]
                    user = interaction.guild.get_member(discord_id)
                    username = user.mention if user else discord_id
                    user_vote_list[str(vote_option)].append(username)

            text = ""
            for option in options_data:
                name = option['option_name']
                id = option['option_id']
                text += f"{name}： {dbdata.get(str(id),0)}票\n"
                if view.show_name:
                    text += ",".join(user_vote_list[str(id)]) + "\n"

            embed = BotEmbed.simple("目前票數",description=f'投票ID：{self.poll_id}\n{text}')
            await interaction.response.send_message(embed=embed,ephemeral=True)

        else:
            await interaction.response.send_message(f"錯誤：此投票只有發起人才能查看結果",ephemeral=True)

class PollCanenlButton(discord.ui.Button):
    def __init__(self,poll_id):
        super().__init__(label="取消投票",custom_id=f"vote_canenl_{poll_id}",style=discord.ButtonStyle.primary)
        self.poll_id = poll_id

    async def callback(self,interaction):
        view:PollView = self.view
        view.sqldb.remove_user_poll(self.poll_id, interaction.user.id)
        await interaction.response.send_message(f"{interaction.user.mention} 已取消投票",ephemeral=True)

class PollNowButton(discord.ui.Button):
    def __init__(self,poll_id):
        super().__init__(label="目前選擇",custom_id=f"vote_now_{poll_id}",style=discord.ButtonStyle.primary)
        self.poll_id = poll_id
    
    async def callback(self,interaction):
        view:PollView = self.view
        data = view.sqldb.get_user_poll(self.poll_id, interaction.user.id)
        if data:
            vote_option = data['vote_option']
            options_data = view.sqldb.get_poll_option(self.poll_id,vote_option)
            await interaction.response.send_message(f"{interaction.user.mention} 投給 {options_data['option_name']}",ephemeral=True)
        else:
            await interaction.response.send_message(f"{interaction.user.mention} 沒有投給任何選項",ephemeral=True)

class PollView(discord.ui.View):
    if TYPE_CHECKING:
        from starcord.DataExtractor import MySQLDatabase
        poll_id: int
        sqldb: MySQLDatabase
        created_id: int
        alternate_account_can_vote: bool
        show_name: bool
        check_results_in_advance: bool
        results_only_initiator: bool
    
    def __init__(self,poll_id,sqldb=None):
        super().__init__(timeout=None)
        self.poll_id = poll_id
        self.sqldb = sqldb
        poll_data = self.sqldb.get_poll(poll_id)
        self.title = poll_data['title']
        self.created_id = poll_data['created_user']
        self.alternate_account_can_vote = bool(poll_data['alternate_account_can_vote'])
        self.show_name = bool(poll_data['show_name'])
        self.check_results_in_advance = bool(poll_data['check_results_in_advance'])
        self.results_only_initiator = bool(poll_data['results_only_initiator'])
        
        self.add_item(PollEndButton(poll_id,self.created_id))
        if self.check_results_in_advance:
            self.add_item(PollResultButton(poll_id))
        self.add_item(PollCanenlButton(poll_id))
        self.add_item(PollNowButton(poll_id))

        
        dbdata = sqldb.get_poll_options(poll_id)
        for option in dbdata:
            custom_id = f"poll_{poll_id}_{option['option_id']}"
            self.add_item(PollOptionButton(label=option['option_name'],poll_id=poll_id, option_id=option['option_id'],custom_id=custom_id))

    def display(self):
        embed = BotEmbed.general(name="投票系統",title=self.title,description=f"投票ID：{self.poll_id}\n- 小帳是否算有效票：{self.alternate_account_can_vote}\n- 結果顯示用戶名：{self.show_name}\n- 只有發起人能查看結果：{self.check_results_in_advance}")
        return embed

class GameView(discord.ui.View):
    def __init__(self,creator,game,number_all,number_now,message):
        super().__init__()
        self.creator = creator
        self.game = game
        self.number_all = number_all
        self.number_now = number_now
        self.message = message
        self.embed = self.create_embed()
        self.participant = [self.creator]

    def create_embed(self):
        embed = BotEmbed.general(f"{self.creator.name} 正在揪團",self.creator.avatar.url,description=self.message)
        embed.add_field(name="主揪",value=self.creator.mention,inline=False)
        embed.add_field(name="遊戲",value=self.game.value)
        embed.add_field(name="人數",value=f"{self.number_now}/{self.number_all}")
        return embed
    
    @discord.ui.button(label="我要加入",style=discord.ButtonStyle.green)
    async def button_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.number_now < self.number_all and interaction.user not in self.participant:
            self.number_now += 1
            await interaction.response.edit_message(embed = self.create_embed(),view=self)
            await interaction.channel.send(f"{interaction.user.mention} 加入遊戲!")
        elif interaction.user.id in self.participant:
            await interaction.response.send_message(f"{interaction.user.mention} 你已經參加此揪團了!",ephemeral=True)
        else:
            await interaction.response.send_message(f"{interaction.user.mention} 很抱歉 揪團已經滿了!",ephemeral=True)

    @discord.ui.button(label="揪團名單",style=discord.ButtonStyle.secondary)
    async def button2_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        list = [user.mention for user in self.participant]
        text = ",".join(list)
        await interaction.response.send_message(f"目前揪團名單:\n{text}",ephemeral=True)

    @discord.ui.button(label="結束揪團",style=discord.ButtonStyle.danger)
    async def button3_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user == self.creator:
            self.disable_all_items()
            await interaction.response.edit_message(view=self)

        else:
            await interaction.response.send_message(f"{interaction.user.mention} 你不是主揪",ephemeral=True)