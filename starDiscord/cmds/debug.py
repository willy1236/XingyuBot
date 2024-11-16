import discord,asyncio,io,matplotlib
from datetime import datetime, timezone, timedelta
from discord.ext import commands,tasks
import matplotlib.pyplot as plt

from starlib import Jsondb,sclient,tz,BotEmbed, debug_guilds, main_guilds, happycamp_guild
from starlib.errors import *
from starlib.utilities.map import sunmon_area
from ..extension import Cog_Extension

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
class MySelectMenus(discord.ui.Select):
    def __init__(self,bot:discord.Bot,guild_id:int,role_ids:list[int]):
        super().__init__(
            placeholder = "Choose a Flavor!",
            min_values = 1,
            max_values = 3,
        )
        self.bot = bot
        self.guild = bot.get_guild(guild_id)
        for role_id in role_ids:
            role = self.guild.get_role(role_id)
            self.append_option(discord.SelectOption(label=role.name, value=str(role.id), description=f"Role ID: {role.id}"))

    async def callback(self, interaction: discord.Interaction):
        lst = []
        for i in self.values:
            role = interaction.guild.get_role(int(i))
            lst.append(role.name)
        await interaction.response.send_message(f"Added role: {','.join(lst)}", ephemeral=True)

class MySelectMenusView(discord.ui.View):
    def __init__(self,bot:discord.Bot,guild_id:int,role_ids:list[int]):
        super().__init__()
        select = MySelectMenus(bot,guild_id,role_ids)
        self.add_item(select)

class debug(Cog_Extension):
    pass
    @commands.is_owner()
    @commands.slash_command(description='測試指令', guild_ids=debug_guilds)
    async def test(self,ctx:discord.ApplicationContext):
        #await ctx.defer()
        # command = self.bot.get_cog('command')
        # await command.dice(ctx,1,100)
        await ctx.respond(view=MySelectMenusView(self.bot,ctx.guild.id,[865582049238843422,866241387166433300,870929961417068565]))

    @commands.is_owner()
    @commands.slash_command(description='幫助測試', guild_ids=debug_guilds)
    async def helptest(self,ctx:discord.ApplicationContext, arg:str):
        if not arg:
            command_names_list = [command.name for command in self.bot.commands]
            await ctx.send(f"{i}. {command.name}" for i, command in enumerate(self.bot.commands, 1))
            await ctx.respond(f"指令列表：{','.join(command_names_list)}")
        else:
            command = self.bot.get_command(arg)
            if not command:
                await ctx.respond(f"找不到指令：{arg}")
            elif isinstance(command, discord.SlashCommandGroup):
                await ctx.respond(f"指令：{command.name}\n描述：{command.description}")
            else:
                command: discord.SlashCommand
                option_str = '\n> '.join([f"{option.name}：{option.description}" for option in command.options])
                await ctx.respond(f"指令：{command.full_parent_name} {command.name}\n描述：{command.description}\n參數：\n> {option_str}")

    @commands.slash_command(description='地圖生成測試')
    async def maptest(self,ctx:discord.ApplicationContext):
        await ctx.defer()
        view = RPG_advanture_panel()
        await ctx.respond(view.map_display(),view=view)
        
        # channel = self.bot.get_channel(566533708371329026)
        # botuser = ctx.guild.get_member(self.bot.user.id)
        # Permission = channel.permissions_for(botuser)
        # await ctx.respond((Permission.send_messages and Permission.embed_links))
    
    @commands.is_owner()
    @commands.slash_command(description='ver.2.0測試', guild_ids=debug_guilds)
    async def embedtest(self, ctx:discord.ApplicationContext):
        embed = BotEmbed.sts()
        embed.add_field(name='測試',value='測試')
        await ctx.respond(embed=embed)

    @commands.is_owner()
    @commands.slash_command(description='更改身分組', guild_ids=happycamp_guild)
    async def roletest(self,ctx:discord.ApplicationContext,old_role:discord.Role):
        await ctx.defer()
        guild = ctx.guild
        #old_role = guild.get_role(984485859132854332)
        new_role = guild.get_role(1250797750174351440)

        for member in old_role.members:
            await member.add_roles(new_role)
            await member.remove_roles(old_role)
            await asyncio.sleep(1)

        await ctx.respond('完成',ephemeral=True)

    @commands.is_owner()
    @commands.slash_command(description='測試指令', guild_ids=debug_guilds)
    async def channeltest(self,ctx:discord.ApplicationContext, channel:discord.Option(discord.TextChannel,required=True,name='頻道',description='通知發送頻道')):
        await ctx.respond(f'{channel.can_send()}',ephemeral=True)

    @commands.is_owner()
    @commands.slash_command(description='連結身分組測試', guild_ids=debug_guilds)
    async def linkedroletest(self,ctx:discord.ApplicationContext):
        role_connection_metadata_records = discord.ApplicationRoleConnectionMetadata(type=discord.ApplicationRoleConnectionMetadataType.boolean_equal,key="metarolekey",name="metarole1",description="metarole1 description")
        data = await self.bot.update_role_connection_metadata_records(role_connection_metadata_records)
        await ctx.respond(f'{data}')
        

    # @commands.slash_command()
    # async def modal_slash(self,ctx: discord.ApplicationContext):
    #     """Shows an example of a modal dialog being invoked from a slash command."""
    #     modal = MyModal(title="Modal Slash Command")
    #     await ctx.send_modal(modal)

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