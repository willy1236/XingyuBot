import discord,asyncio
from datetime import datetime, timezone, timedelta,time
from discord.ext import commands,tasks

from core.classes import Cog_Extension
from bothelper import Jsondb
from bothelper.errors import *

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
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.add_item(discord.ui.InputText(label="Short Input"))
        self.add_item(discord.ui.InputText(label="Long Input", style=discord.InputTextStyle.long))

    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Modal Results")
        embed.add_field(name="Short Input", value=self.children[0].value)
        embed.add_field(name="Long Input", value=self.children[1].value)
        await interaction.response.send_message(embeds=[embed])

class debug(Cog_Extension):
    pass
    # @commands.slash_command(description='測試指令')
    # async def test(self,ctx):
    #     raise MysqlError1()
    #     await ctx.respond(f'done {data}')

    # @commands.slash_command()
    # async def modal_slash(self,ctx: discord.ApplicationContext):
    #     """Shows an example of a modal dialog being invoked from a slash command."""
    #     modal = MyModal(title="Modal via Slash Command")
    #     await ctx.send_modal(modal)
    
    # @commands.command()
    # @commands.is_owner()
    # async def embed(self,ctx,msg):
    #     embed=discord.Embed(title="Bot Radio Station",description=f'{msg}',color=0xc4e9ff)
    #     embed.set_footer(text='廣播電台 | 機器人全群公告')
    #     await ctx.send(embed=embed)

    # @commands.command()
    # @commands.is_owner()
    # async def debug(self,ctx,role):
    #     role = await find.role(ctx,role)
    #     dict = {}
    #     dict[str(role.id)] = {}
    #     dict[str(role.id)]['name']=role.name
    #     dict[str(role.id)]['color']=role.color.to_rgb()
    #     dict[str(role.id)]['time']=role.created_at.strftime('%Y%m%d')
    #     print(dict)
    
    # @commands.command()
    # @commands.is_owner()
    # async def task_test(self, ctx,arg):
    #     task = tasks.Loop.get_task(arg)
    #     print(task)
    #     if task:
    #         ctx.send(task.is_running())
    #     else:
    #         ctx.send('Not found')

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