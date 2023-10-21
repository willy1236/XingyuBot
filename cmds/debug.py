import discord,asyncio,io,matplotlib
from datetime import datetime, timezone, timedelta
from discord.ext import commands,tasks
import matplotlib.pyplot as plt

from core.classes import Cog_Extension
from starcord import Jsondb
from starcord.errors import *
from starcord.types.game import DBGame
from starcord.rpg.map import sunmon_area

tz = timezone(timedelta(hours=+8))

# Note that custom_ids can only be up to 100 characters long.
class PersistentView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Green",style=discord.ButtonStyle.green,custom_id="persistent_view:green")
    async def green(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message("This is green.", ephemeral=True)

    @discord.ui.button(label="Red", style=discord.ButtonStyle.red, custom_id="persistent_view:red")
    async def red(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message("This is red.", ephemeral=True)

    @discord.ui.button(label="Grey", style=discord.ButtonStyle.grey, custom_id="persistent_view:grey")
    async def grey(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message("This is grey.", ephemeral=True)

class MyModal(discord.ui.Modal):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.add_item(discord.ui.InputText(label="Short Input"))
        self.add_item(discord.ui.InputText(label="Long Input", style=discord.InputTextStyle.long))

    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Modal Results")
        embed.add_field(name="Short Input", value=self.children[0].value)
        embed.add_field(name="Long Input", value=self.children[1].value)
        await interaction.response.send_message(embeds=[embed])

map_dict = {
    "0": "⬛",
    "1": "◻️",
    "2": "🟨"
}

class RPG_advanture_panel(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.map_l = 14
        self.map_w = 14
        self.area = sunmon_area(self.map_l,self.map_w)
        self.player_x = 0
        self.player_y = 0
        self.text = ''
        
    def map_display(self):
        self.text = ''
        #area_display = copy.deepcopy(self.area)
        area_display = []
        for i in self.area:
            row = []
            for j in i:
                row.append(map_dict.get(j))
            area_display.append(row)
        area_display[self.player_y][self.player_x] = map_dict.get('2')
        for i in area_display:
            self.text += " ".join(i) + '\n'
        return self.text

    @discord.ui.button(label="↑",style=discord.ButtonStyle.green)
    async def up(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.player_y != 0 and self.area[self.player_y-1][self.player_x] == '0':
            self.player_y -= 1
            await interaction.response.edit_message(content=self.map_display(),view=self)
        else:
            await interaction.response.edit_message(content=self.text,view=self)

    @discord.ui.button(label="↓",style=discord.ButtonStyle.green)
    async def down(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.player_y != self.map_l-1 and self.area[self.player_y+1][self.player_x] == '0':
            self.player_y += 1
            if self.player_x == self.map_w-1 and self.player_y == self.map_l-1:
                self.disable_all_items()
                await interaction.response.edit_message(content=f'恭喜完成~\n{self.map_display()}',view=self)
            else:
                await interaction.response.edit_message(content=self.map_display(),view=self)
        else:
            await interaction.response.edit_message(content=self.text,view=self)

    @discord.ui.button(label="←",style=discord.ButtonStyle.green)
    async def left(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.player_x != 0 and self.area[self.player_y][self.player_x-1] == '0':
            self.player_x -= 1
            await interaction.response.edit_message(content=self.map_display(),view=self)
        else:
            await interaction.response.edit_message(content=self.text,view=self)
    
    @discord.ui.button(label="→",style=discord.ButtonStyle.green)
    async def right(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.player_x != self.map_w-1 and self.area[self.player_y][self.player_x+1] == '0':
            self.player_x += 1
            if self.player_x == self.map_w-1 and self.player_y == self.map_l-1:
                self.disable_all_items()
                await interaction.response.edit_message(content=f'恭喜完成~\n{self.map_display()}',view=self)
            else:
                await interaction.response.edit_message(content=self.map_display(),view=self)
        else:
            await interaction.response.edit_message(content=self.text,view=self)

class debug(Cog_Extension):
    pass
    @commands.is_owner()
    @commands.slash_command(description='測試指令')
    async def test(self,ctx:discord.ApplicationContext):
        await ctx.defer()
        
        def data_string(s,d):
            t = int(round(s/100.*sum(d)))     # 透過百分比反推原本的數值
            return f'{t}\n（{s:.1f}%）'

        # 字形
        matplotlib.rc('font', family='Microsoft JhengHei')
        # 資料
        labels = ['A', 'B', 'C', 'D']
        sizes = [1, 3, 2, 5]  # 各部分的百分比

        # 設置顏色
        colors = ['gold', 'yellowgreen', 'lightcoral', 'lightskyblue']

        # 設置圓餅圖的突出顯示
        #explode = (0.1, 0, 0, 0)  # 將第一塊突出顯示
    
        # 繪製圓餅圖
        plt.pie(sizes, labels=labels, colors=colors, autopct=lambda i: data_string(i,sizes), shadow=False, startangle=140)

        # 添加標題
        plt.title('圓餅圖範例')

        image_buffer = io.BytesIO()
        plt.savefig(image_buffer, format='png', dpi=200, bbox_inches='tight')
        image_buffer.seek(0)

        await ctx.respond(file=discord.File(image_buffer,filename="pie.png"))

    @commands.slash_command(description='地圖生成測試')
    async def maptest(self,ctx:discord.ApplicationContext):
        await ctx.defer()
        view = RPG_advanture_panel()
        await ctx.respond(view.map_display(),view=view)
        
        # channel = self.bot.get_channel(566533708371329026)
        # botuser = ctx.guild.get_member(self.bot.user.id)
        # Permission = channel.permissions_for(botuser)
        # await ctx.respond((Permission.send_messages and Permission.embed_links))
    
    # @commands.slash_command()
    # async def modal_slash(self,ctx: discord.ApplicationContext):
    #     """Shows an example of a modal dialog being invoked from a slash command."""
    #     modal = MyModal(title="Modal Slash Command")
    #     await ctx.send_modal(modal)

    # @commands.command()
    # @commands.is_owner()
    # async def prepare(self,ctx: commands.Context):
    #     """Starts a persistent view."""
    #     # In order for a persistent view to be listened to, it needs to be sent to an actual message.
    #     # Call this method once just to store it somewhere.
    #     # In a more complicated program you might fetch the message_id from a database for use later.
    #     # However this is outside of the scope of this simple example.
    #     await ctx.send("What's your favourite colour?", view=PersistentView(self))
    
    # @commands.command()
    # @commands.is_owner()
    # async def derole(self,ctx: commands.Context):
    #     role = self.bot.get_guild(613747262291443742).get_role(706794165094187038)
    #     channel = self.bot.get_channel(706810474326655026)
    #     permission = discord.Permissions(view_channel=True)
    #     #overwrites = {}
    #     for user in role.members:
    #         #overwrites[user] = discord.PermissionOverwrite(view_channel=True)    
    #         await channel.set_permissions(user,view_channel=True)
    #         await asyncio.sleep(0.5)
    #     await ctx.message.add_reaction('✅')

def setup(bot):
    bot.add_cog(debug(bot))