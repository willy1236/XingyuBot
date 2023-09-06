import discord,datetime
from starcord.database import sqldb
from starcord.utility import BotEmbed

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
            for option in options_data:
                name = option['option_name']
                id = option['option_id']
                text += f"{name}： {dbdata.get(str(id),0)}票\n"

            embed = BotEmbed.simple(polldata["title"],description=f'投票ID：{self.poll_id}\n{text}')
            await interaction.response.edit_message(embed=embed,view=self)
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
