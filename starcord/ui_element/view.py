import discord,datetime,matplotlib,io
from typing import TYPE_CHECKING
from starcord.Utilities import BotEmbed

class PollOptionButton(discord.ui.Button):
    def __init__(self,label,poll_id,option_id,custom_id):
        super().__init__(label=label,custom_id=custom_id)
        self.poll_id = poll_id
        self.option_id = option_id
    
    async def callback(self,interaction):
        view:PollView = self.view
        can_vote = False
        have_only_role = False
        vote_magnification = 1
        if view.role_dict:
            for roleid in view.role_dict:
                if view.role_dict[roleid][0] == 1:
                    have_only_role = True
                    role = interaction.user.get_role(roleid)
                    if role:
                        can_vote = True

                if view.role_dict[roleid][1] > vote_magnification:
                    vote_magnification = view.role_dict[roleid][1]
        
        if not view.role_dict or (have_only_role and can_vote):
            r = view.sqldb.set_user_poll(self.poll_id,interaction.user.id,self.option_id,datetime.datetime.now(),vote_magnification)
            if r == 1:
                await interaction.response.send_message(f"{interaction.user.mention} 已投票給 {self.label} {vote_magnification} 票",ephemeral=True)
            else:
                await interaction.response.send_message(f"{interaction.user.mention} 已取消投票給 {self.label}",ephemeral=True)
        else:
            await interaction.response.send_message(f"{interaction.user.mention}：你沒有投票資格",ephemeral=True)

class PollEndButton(discord.ui.Button):
    def __init__(self,poll_id,created_id,bot:discord.Bot):
        super().__init__(label="結算投票",custom_id=f"end_poll_{poll_id}",style=discord.ButtonStyle.danger)
        self.poll_id = poll_id
        self.created_id = created_id
        self.bot = bot

    async def callback(self,interaction):
        if interaction.user.id == self.created_id or (self.bot and await self.bot.is_owner(interaction.user)):
            view:PollView = self.view
            view.clear_items()
            view.sqldb.update_poll(self.poll_id,"is_on",0)
            
            polldata = view.sqldb.get_poll(self.poll_id)
            text, labels, sizes = view.results_text(interaction,True)

            import matplotlib.pyplot as plt
            fig, ax = plt.subplots()
            #圖表製作
            def data_string(s,d) -> str:
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

            embed = BotEmbed.simple(polldata["title"],description=f'{text}')
            embed.set_footer(text=f"投票ID：{self.poll_id}")
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
            text = view.results_text(interaction)
            embed = BotEmbed.simple("目前票數",description=f'{text}')
            embed.set_footer(text=f"投票ID：{self.poll_id}")
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
        from starcord.Core import DiscordBot
        poll_id: int
        sqldb: MySQLDatabase
        bot: DiscordBot
        guild_id: int
        message_id: int | None
        title: str
        created_id: int
        alternate_account_can_vote: bool
        show_name: bool
        check_results_in_advance: bool
        results_only_initiator: bool
        multiple_choice: bool

    def __init__(self,poll_id,sqldb=None,bot=None):
        super().__init__(timeout=None)
        self.poll_id = poll_id
        self.sqldb = sqldb
        self.bot = bot
        self._role_dict = {}
        
        poll_data = self.sqldb.get_poll(poll_id)
        self.title = poll_data['title']
        self.created_id = poll_data['created_user']
        self.alternate_account_can_vote = bool(poll_data['alternate_account_can_vote'])
        self.show_name = bool(poll_data['show_name'])
        self.check_results_in_advance = bool(poll_data['check_results_in_advance'])
        self.results_only_initiator = bool(poll_data['results_only_initiator'])
        self.multiple_choice = bool(poll_data['multiple_choice'])
        # TODO: number_of_user_votes (replace multiple_choice)
        # TODO: change_vote (decide if user can change his/her vote or not)

        
        self.guild_id = poll_data['guild_id']
        self.message_id = poll_data['message_id']

        self.add_item(PollEndButton(poll_id,self.created_id,bot))
        if self.check_results_in_advance:
            self.add_item(PollResultButton(poll_id))
        self.add_item(PollCanenlButton(poll_id))
        self.add_item(PollNowButton(poll_id))

        
        dbdata = sqldb.get_poll_options(poll_id)
        for option in dbdata:
            custom_id = f"poll_{poll_id}_{option['option_id']}"
            self.add_item(PollOptionButton(label=option['option_name'],poll_id=poll_id, option_id=option['option_id'],custom_id=custom_id))
    
    @property
    def role_dict(self) -> dict:
        if not self._role_dict:
            dbdata = self.sqldb.get_poll_role(self.poll_id)
            self._role_dict = {}
            if dbdata:
                for data in dbdata:
                    role_id = data['role_id']
                    role_type = data['role_type']
                    role_magnification = data['role_magnification']
                    self._role_dict[role_id] = [role_type,role_magnification]
        return self._role_dict
        
    def embed(self,guild:discord.Guild):
        """guild: 提供投票所在的伺服器"""
        only_role_list = []
        role_magification_list = []
        for roleid in self.role_dict:
            role = guild.get_role(roleid)
            if self.role_dict[roleid][0] == 1:
                only_role_list.append(role.mention if role else roleid)
            if self.role_dict[roleid][1] > 1:
                mag = self.role_dict[roleid][1]
                role_magification_list.append(f"{role.mention}({mag})" if role else f"{roleid}({mag})")
        
        description = f"- 顯示投票人：{self.show_name}\n- 僅限發起人能查看結果：{self.results_only_initiator}\n- 多選：{self.multiple_choice}"
        if self.alternate_account_can_vote:
            description += f"\n- 小帳是否算有效票：{self.alternate_account_can_vote}"

        if only_role_list:
            description += "\n- 可投票身分組：" + ",".join(only_role_list)
        if role_magification_list:
            description += "\n- 身分組投票權重：" + ",".join(role_magification_list)
        embed = BotEmbed.general(name="投票系統",title=self.title,description=description)
        embed.set_footer(text=f"投票ID：{self.poll_id}")

        author = guild.get_member(self.created_id)
        if author:
            embed.set_author(name=author.name, icon_url=author.avatar.url)
        return embed
    
    def results_text(self,interaction,labels_and_sizes=False) -> tuple[str, list, list] | str:
        vote_count_data = self.sqldb.get_poll_vote_count(self.poll_id, self.alternate_account_can_vote)
        options_data = self.sqldb.get_poll_options(self.poll_id)

        if self.show_name:
            user_vote_data = self.sqldb.get_users_poll(self.poll_id,self.alternate_account_can_vote)
            user_vote_list = {}
            for i in range(1,len(options_data) + 1):
                user_vote_list[str(i)] = [] 

            for i in user_vote_data:
                discord_id = i["discord_id"]
                vote_option = i["vote_option"]
                vote_magnification = i.get("vote_magnification",1)
                user = interaction.guild.get_member(discord_id)
                username = user.mention if user else discord_id
                if vote_magnification != 1:
                    username += f"({vote_magnification})"
                user_vote_list[str(vote_option)].append(username)

        text = ""
        if labels_and_sizes:
            labels = []
            sizes = []

        for option in options_data:
            name = option['option_name']
            id = option['option_id']
            count = vote_count_data.get(str(id),0)
            text += f"{name}： {count}票\n"
            
            if self.show_name:
                text += ",".join(user_vote_list[str(id)]) + "\n"

            if labels_and_sizes and count > 0:
                labels.append(name)
                sizes.append(count)
        
        if labels_and_sizes:
            return text, labels, sizes
        else:
            return text
        
class ElectionPollView(PollView):
    if TYPE_CHECKING:
        from starcord.DataExtractor import MySQLDatabase
        from starcord.Core import DiscordBot
        poll_id: int
        sqldb: MySQLDatabase
        bot: DiscordBot
    
    def __init__(self,poll_id,sqldb=None,bot=None):
        self.add_item(PollEndButton(poll_id,self.created_id,bot))
        if self.check_results_in_advance:
            self.add_item(PollResultButton(poll_id))
        self.add_item(PollCanenlButton(poll_id))
        self.add_item(PollNowButton(poll_id))

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

class WelcomeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="按下按鈕進入伺服器",style=discord.ButtonStyle.green,custom_id="welcome_1")
    async def button2_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        role = interaction.guild.get_role(1190269561891737690)
        await interaction.user.add_roles(role)        
        await interaction.response.send_message(f"{interaction.user.mention} 歡迎加入！",ephemeral=True)

class ReactionRole1(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def reaction_role(self,interaction: discord.Interaction,roleid:int):
        role = interaction.guild.get_role(roleid)
        if interaction.user.get_role(roleid):
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"已移除 {role.name} 身分組！",ephemeral=True)
        else:
            await interaction.user.add_roles(role)        
            await interaction.response.send_message(f"已給予 {role.name} 身分組！",ephemeral=True)

    @discord.ui.button(label="League of Legends",style=discord.ButtonStyle.primary,custom_id="ReactionRole1_1")
    async def button1_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        roleid = 1201020961684738128
        await self.reaction_role(interaction,roleid)

    @discord.ui.button(label="魔物獵人",style=discord.ButtonStyle.primary,custom_id="ReactionRole1_2")
    async def button2_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        roleid = 1201020985147666472
        await self.reaction_role(interaction,roleid)

    @discord.ui.button(label="日麻",style=discord.ButtonStyle.primary,custom_id="ReactionRole1_3")
    async def button3_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        roleid = 1201021022179176538
        await self.reaction_role(interaction,roleid)

    @discord.ui.button(label="APEX",style=discord.ButtonStyle.primary,custom_id="ReactionRole1_4")
    async def button4_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        roleid = 1201021043284922460
        await self.reaction_role(interaction,roleid)

    @discord.ui.button(label="特戰英豪",style=discord.ButtonStyle.primary,custom_id="ReactionRole1_5")
    async def button5_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        roleid = 1201021066454241443
        await self.reaction_role(interaction,roleid)

    @discord.ui.button(label="OSU",style=discord.ButtonStyle.primary,custom_id="ReactionRole1_6")
    async def button6_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        roleid = 1201021221299560581
        await self.reaction_role(interaction,roleid)
    
    @discord.ui.button(label="NSFW",style=discord.ButtonStyle.primary,custom_id="ReactionRole1_7")
    async def button7_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        roleid = 1201350881422082129
        await self.reaction_role(interaction,roleid)