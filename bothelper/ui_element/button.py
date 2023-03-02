import discord
from bothelper.database import sqldb

class ReactRole_button(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="音樂DJ",custom_id="Reactbutton1-1",row=1,style=discord.ButtonStyle.primary)
    async def button_callback1(self, button: discord.ui.Button, interaction: discord.Interaction):
        #bot = interaction.client
        role = interaction.guild.get_role(619893837833306113)
        user = interaction.user
        if role in user.roles:
            await user.remove_roles(role)
            await interaction.response.send_message(content="音樂DJ 已移除",ephemeral=True)
        else:
            await user.add_roles(role)
            await interaction.response.send_message(content="音樂DJ 已給予",ephemeral=True)

    @discord.ui.button(label="抹茶人，我的超人",custom_id="Reactbutton1-2",row=1,style=discord.ButtonStyle.primary)
    async def button_callback2(self, button: discord.ui.Button, interaction: discord.Interaction):
        role = interaction.guild.get_role(1000680995307143218)
        user = interaction.user
        if role in user.roles:
            await user.remove_roles(role)
            await interaction.response.send_message(content="抹茶人，我的超人 已移除",ephemeral=True)
        else:
            await user.add_roles(role)
            await interaction.response.send_message(content="抹茶人，我的超人 已給予",ephemeral=True)

    @discord.ui.button(label="綜合遊戲區",custom_id="Reactbutton1-3",row=1,style=discord.ButtonStyle.primary)
    async def button_callback3(self, button: discord.ui.Button, interaction: discord.Interaction):
        role = interaction.guild.get_role(858558233403719680)
        user = interaction.user
        if role in user.roles:
            await user.remove_roles(role)
            await interaction.response.send_message(content="綜合遊戲區 已移除",ephemeral=True)
        else:
            await user.add_roles(role)
            await interaction.response.send_message(content="綜合遊戲區 已給予",ephemeral=True)
        
    # @discord.ui.button(label="遊戲狂熱者",custom_id="Reactbutton1-4",row=2,style=discord.ButtonStyle.secondary)
    # async def button_callback4(self, button: discord.ui.Button, interaction: discord.Interaction):
    #     role = interaction.guild.get_role(858558233403719680)
    #     user = interaction.user
    #     bot = interaction.client
    #     channel = bot.get_channel(706810474326655026)
    #     if user in channel.overwrites:
    #         user = interaction.user
    #         await channel.set_permissions(user,view_channel=None,reason='身分組選擇:移除')
    #         await interaction.response.send_message(content="遊戲狂熱區 已移除權限",ephemeral=True)
    #     else:
    #         await channel.set_permissions(user,view_channel=True,reason='身分組選擇:加入')
    #         await interaction.response.send_message(content="遊戲狂熱區 已給予權限",ephemeral=True)
    
    @discord.ui.button(label="VT&實況區",custom_id="Reactbutton1-4",row=1,style=discord.ButtonStyle.primary)
    async def button_callback4(self, button: discord.ui.Button, interaction: discord.Interaction):
        role = interaction.guild.get_role(1012754715123134524)
        user = interaction.user
        if role in user.roles:
            await user.remove_roles(role)
            await interaction.response.send_message(content="VT&實況區 已移除",ephemeral=True)
        else:
            await user.add_roles(role)
            await interaction.response.send_message(content="VT&實況區 已給予",ephemeral=True)

class Delete_Pet_button(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)

    @discord.ui.button(label="放生寵物",style=discord.ButtonStyle.danger)
    async def button_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        user = interaction.user
        sqldb.delete_user_pet(str(user.id))
        button.disabled = True
        await interaction.response.edit_message(content="寵物已放生",view=self)