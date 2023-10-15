import discord,datetime,matplotlib,io
from starcord.database import sqldb
from starcord.utility import BotEmbed
import matplotlib.pyplot as plt

class PollOptionButton(discord.ui.Button):
    def __init__(self,label,poll_id,option_id,custom_id):
        super().__init__(label=label,custom_id=custom_id)
        self.poll_id = poll_id
        self.option_id = option_id
    
    async def callback(self,interaction):
        sqldb.add_user_poll(self.poll_id,interaction.user.id,self.option_id,datetime.datetime.now())
        await interaction.response.send_message(f"{interaction.user.mention} 已投票給 {self.label}",ephemeral=True)
    

class PollView(discord.ui.View):
    def __init__(self,poll_id):
        super().__init__(timeout=None)
        self.poll_id = poll_id
        self.created_id = sqldb.get_poll(poll_id)['created_user']
        dbdata = sqldb.get_poll_options(poll_id)
        for option in dbdata:
            custom_id = f"poll_{option['option_id']}"
            self.add_item(PollOptionButton(label=option['option_name'],poll_id=poll_id, option_id=option['option_id'],custom_id=custom_id))

    @discord.ui.button(label="結算投票",custom_id="end_poll",style=discord.ButtonStyle.danger)
    async def end_button_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user.id == self.created_id:
            self.disable_all_items()
            sqldb.update_poll(self.poll_id,"is_on",0)
            
            polldata = sqldb.get_poll(self.poll_id)
            dbdata = sqldb.get_poll_vote_count(self.poll_id)
            options_data = sqldb.get_poll_options(self.poll_id)

            text = ""
            labels = []
            sizes = []
            for option in options_data:
                name = option['option_name']
                id = option['option_id']
                count = dbdata.get(str(id),0)
                text += f"{name}： {count}票\n"

                if count > 0:
                    labels.append(name)
                    sizes.append(count)

            #圖表製作
            def data_string(s,d):
                t = int(round(s/100.*sum(d)))     # 透過百分比反推原本的數值
                return f'{t}\n（{s:.1f}%）'

            # 字形
            matplotlib.rc('font', family='Microsoft JhengHei')

            # 設置顏色
            colors = ['gold', 'yellowgreen', 'lightcoral', 'lightskyblue']

            # 設置圓餅圖的突出顯示
            #explode = (0.1, 0, 0, 0)  # 將第一塊突出顯示
        
            # 繪製圓餅圖
            plt.pie(sizes, labels=labels, colors=colors, autopct=lambda i: data_string(i,sizes), shadow=False, startangle=140)

            # 添加標題
            plt.title(polldata['title'])

            image_buffer = io.BytesIO()
            plt.savefig(image_buffer, format='png', dpi=200, bbox_inches='tight')
            image_buffer.seek(0)

            embed = BotEmbed.simple(polldata["title"],description=f'投票ID：{self.poll_id}\n{text}')
            await interaction.response.edit_message(embed=embed,view=self,file=discord.File(image_buffer,filename="pie.png"))
        else:
            await interaction.response.send_message(f"錯誤：只有投票發起人才能結算",ephemeral=True)

    @discord.ui.button(label="查看結果",custom_id="poll_result",style=discord.ButtonStyle.primary)
    async def result_button_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        dbdata = sqldb.get_poll_vote_count(self.poll_id)
        options_data = sqldb.get_poll_options(self.poll_id)

        text = ""
        for option in options_data:
            name = option['option_name']
            id = option['option_id']
            text += f"{name}： {dbdata.get(str(id),0)}票\n"

        embed = BotEmbed.simple("目前票數",description=f'投票ID：{self.poll_id}\n{text}')
        await interaction.response.send_message(embed=embed,ephemeral=True)

    @discord.ui.button(label="取消投票",custom_id="vote_canenl",style=discord.ButtonStyle.primary)
    async def canenl_button_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        sqldb.remove_user_poll(self.poll_id, interaction.user.id)
        await interaction.response.send_message(f"{interaction.user.mention} 已取消投票",ephemeral=True)

    @discord.ui.button(label="目前選擇",custom_id="vote_now",style=discord.ButtonStyle.primary)
    async def now_button_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        data = sqldb.get_user_poll(self.poll_id, interaction.user.id)
        if data:
            vote_option = data['vote_option']
            options_data = sqldb.get_poll_option(self.poll_id,vote_option)
            await interaction.response.send_message(f"{interaction.user.mention} 投給 {options_data['option_name']}",ephemeral=True)
        else:
            await interaction.response.send_message(f"{interaction.user.mention} 沒有投給任何選項",ephemeral=True)