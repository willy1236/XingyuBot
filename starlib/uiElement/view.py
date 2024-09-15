from __future__ import annotations

import io
from datetime import datetime
from typing import TYPE_CHECKING
from decimal import Decimal

import discord
import matplotlib

from ..utilities import BotEmbed

if TYPE_CHECKING:
    from starlib.core import DiscordBot
    from starlib.database import MySQLDatabase, SQLEngine
    from starlib.models.mysql import Poll, PollOption

class PollOptionButton(discord.ui.Button):
    def __init__(self,option:PollOption, custom_id:str, row:int=None):
        super().__init__(label=option.option_name,custom_id=custom_id,row=row)
        self.option = option
    
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
            r = view.sqldb.set_user_poll(self.option.poll_id,interaction.user.id,self.option.option_id,datetime.now(),vote_magnification, view.poll.number_of_user_votes)
            if r == 2:
                await interaction.response.send_message(f"{interaction.user.mention} 已投了 {view.poll.number_of_user_votes} 票而無法投票",ephemeral=True)
            elif r == 1:
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
            view.poll.is_on = 0
            view.sqldb.update_poll(view.poll)

            embed, labels, sizes = view.results_embed(interaction,True)
            image_buffer = view.generate_chart(labels, sizes)

            
            await interaction.response.edit_message(embed=embed,view=view,file=discord.File(image_buffer,filename="pie.png"))
        else:
            await interaction.response.send_message(f"錯誤：只有投票發起人才能結算",ephemeral=True)
            
class PollResultButton(discord.ui.Button):
    def __init__(self,poll_id):
        super().__init__(label="查看結果",custom_id=f"poll_result_{poll_id}",style=discord.ButtonStyle.primary)
        self.poll_id = poll_id

    async def callback(self,interaction):
        view:PollView = self.view    
        if not view.poll.results_only_initiator:
            embed = view.results_embed(interaction)
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
        dbdata = view.sqldb.get_user_poll(self.poll_id, interaction.user.id)
        if dbdata:
            vote_mag = dbdata[0][0].vote_magnification
            options_name = ",".join([data[1] for data in dbdata])
            await interaction.response.send_message(f"{interaction.user.mention} 投給 {options_name} {vote_mag}票",ephemeral=True)
        else:
            await interaction.response.send_message(f"{interaction.user.mention} 沒有投給任何選項",ephemeral=True)

class PollView(discord.ui.View):
    if TYPE_CHECKING:
        poll = Poll
        sqldb: SQLEngine
        bot: DiscordBot | None

    def __init__(self,poll:Poll,sqldb,bot=None):
        super().__init__(timeout=None)
        self.poll = poll
        self.sqldb = sqldb
        self.bot = bot
        self._role_dict = {}
        # TODO: change_vote (decide if user can change his/her vote or not)
        

        self.add_item(PollEndButton(poll.poll_id,self.poll.created_user,bot))
        if self.poll.check_results_in_advance:
            self.add_item(PollResultButton(poll.poll_id))
        self.add_item(PollCanenlButton(poll.poll_id))
        self.add_item(PollNowButton(poll.poll_id))

        
        dbdata = self.sqldb.get_poll_options(poll.poll_id)
        i = 5
        for option in dbdata:
            custom_id = f"poll_{poll.poll_id}_{option.option_id}"
            self.add_item(PollOptionButton(option=option, custom_id=custom_id, row=int(i/5)))
            i += 1
    
    @property
    def role_dict(self) -> dict:
        if not self._role_dict:
            dbdata = self.sqldb.get_poll_role(self.poll.poll_id)
            self._role_dict = {}
            if dbdata:
                for data in dbdata:
                    role_id = data.role_id
                    role_type = data.role_type
                    role_magnification = data.role_magnification
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
        
        description = ""
        description += "- 使用投票實名制" if self.poll.show_name else "- 匿名投票"
        description += ("\n- 僅限發起人能預先查看結果" if self.poll.results_only_initiator else "\n- 所有人都能預先查看結果") if self.poll.check_results_in_advance else "\n- 結果將在結束時公佈"
        description += f"\n- 可選擇 {self.poll.number_of_user_votes} 個選項"
        if self.poll.ban_alternate_account_voting:
            description += f"\n- 小帳不算有效票"

        if only_role_list:
            description += "\n- 可投票身分組：" + ",".join(only_role_list)
        if role_magification_list:
            description += "\n- 身分組投票權重：" + ",".join(role_magification_list)
        embed = BotEmbed.general(name="投票系統",title=self.poll.title,description=description)
        embed.set_footer(text=f"投票ID：{self.poll.poll_id}")

        author = guild.get_member(self.poll.created_user)
        if author:
            embed.set_author(name=author.name, icon_url=author.avatar.url)
        return embed
    
    def results_embed(self, interaction: discord.Interaction, labels_and_sizes=False) -> tuple[discord.Embed, list, list] | discord.Embed:
        """
        Generates an embed object containing the results of a poll.

        Args:
            interaction (discord.Interaction): The interaction object representing the poll.
            labels_and_sizes (bool, optional): Whether to include labels and sizes for each option. Defaults to False.

        Returns:
            tuple[discord.Embed, list, list] | discord.Embed: If `labels_and_sizes` is True, returns a tuple containing the embed object, a list of labels, and a list of sizes. 
            If `labels_and_sizes` is False, returns only the embed object.
        """
        vote_count_data = self.sqldb.get_poll_vote_count(self.poll.poll_id, not self.poll.ban_alternate_account_voting)
        options_data = self.sqldb.get_poll_options(self.poll.poll_id)

        if self.poll.show_name:
            user_vote_data = self.sqldb.get_users_poll(self.poll.poll_id, not self.poll.ban_alternate_account_voting)
            user_vote_list = {}
            for i in range(1, len(options_data) + 1):
                user_vote_list[str(i)] = []

            for i in user_vote_data:
                discord_id = i.discord_id
                vote_option = i.vote_option
                vote_magnification = i.vote_magnification

                user = interaction.guild.get_member(discord_id)
                username = user.mention if user else f"<@{discord_id}>"
                if vote_magnification != 1:
                    username += f"({vote_magnification})"
                user_vote_list[str(vote_option)].append(username)

        text = ""
        if labels_and_sizes:
            labels = []
            sizes = []

        for option in options_data:
            name = option.option_name
            id = option.option_id
            count = vote_count_data.get(str(id), 0)
            text += f"{name}： {count}票\n"

            if self.poll.show_name:
                text += ",".join(user_vote_list[str(id)]) + "\n"

            if labels_and_sizes and count > 0:
                labels.append(name)
                sizes.append(count)

        embed = BotEmbed.simple(self.poll.title, description=text)
        embed.set_footer(text=f"投票ID：{self.poll.poll_id}")

        if labels_and_sizes:
            return embed, labels, sizes
        else:
            return embed
        
    def generate_chart(self,labels,sizes):
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        #圖表製作
        def data_string(s,d) -> str:
            t = int(round(s/100. * float(sum(d))))     # 透過百分比反推原本的數值
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
        ax.set_title(self.poll.title)
        #plt.title()

        image_buffer = io.BytesIO()
        plt.savefig(image_buffer, format='png', dpi=200, bbox_inches='tight')
        image_buffer.seek(0)
        
        return image_buffer

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

class SakagawaReactionRole(discord.ui.View):
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

class WelcomeView(SakagawaReactionRole):
    @discord.ui.button(label="按下按鈕進入伺服器",style=discord.ButtonStyle.green,custom_id="welcome_1")
    async def button2_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        role = interaction.guild.get_role(1190269561891737690)
        await interaction.user.add_roles(role)        
        await interaction.response.send_message(f"{interaction.user.mention} 歡迎加入！",ephemeral=True)

class ReactionRole1(SakagawaReactionRole):
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
    
    @discord.ui.button(label="NSFW",style=discord.ButtonStyle.danger,custom_id="ReactionRole1_7")
    async def button7_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        roleid = 1201350881422082129
        await self.reaction_role(interaction,roleid)

class ReactionRole2(SakagawaReactionRole):
    @discord.ui.button(label="開台通知",style=discord.ButtonStyle.primary,custom_id="ReactionRole2_1")
    async def button1_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        roleid = 1221128533779284108
        await self.reaction_role(interaction,roleid)