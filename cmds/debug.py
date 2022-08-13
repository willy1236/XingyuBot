import discord,json,requests,asyncio
from datetime import datetime, timezone, timedelta,time
from discord.ext import commands,tasks

from core.classes import Cog_Extension
from BotLib.funtions import *
from BotLib.userlib import *


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

class debug(Cog_Extension):
    db = Database()
    rsdata = db.rsdata

    @commands.command()
    @commands.is_owner()
    async def embed(self,ctx,msg):
        embed=discord.Embed(title="Bot Radio Station",description=f'{msg}',color=0xc4e9ff)
        embed.set_footer(text='廣播電台 | 機器人全群公告')
        
        await ctx.send(embed=embed)

    @commands.command()
    @commands.is_owner()
    async def debug(self,ctx,role):
        role = await find.role(ctx,role)
        dict = {}
        dict[str(role.id)] = {}
        dict[str(role.id)]['name']=role.name
        dict[str(role.id)]['color']=role.color.to_rgb()
        dict[str(role.id)]['time']=role.created_at.strftime('%Y%m%d')
        print(dict)
                
    @commands.command()
    @commands.is_owner()
    async def rq(self,ctx):
        url = f'https://api.mozambiquehe.re/crafting?auth={Database().apex_status_API}'
        headers ={

        }

        response = requests.get(url, headers=headers)
        print(response)

    @commands.command()
    @commands.is_owner()
    async def test(self, ctx):
        #dcuser = find.user2(arg=arg)
        #print(dcuser)
        pt = User(ctx.author.id).point
        #print(pt)
    
    @commands.command()
    @commands.is_owner()
    async def task_test(self, ctx,arg):
        task = tasks.Loop.get_task(arg)
        print(task)
        if task:
            ctx.send(task.is_running())
        else:
            ctx.send('Not found')

    @commands.command()
    @commands.is_owner()
    async def prepare(self,ctx: commands.Context):
        """Starts a persistent view."""
        # In order for a persistent view to be listened to, it needs to be sent to an actual message.
        # Call this method once just to store it somewhere.
        # In a more complicated program you might fetch the message_id from a database for use later.
        # However this is outside of the scope of this simple example.
        await ctx.send("What's your favourite colour?", view=PersistentView(self))
    
    @commands.command()
    @commands.is_owner()
    async def derole(self,ctx: commands.Context):
        role = self.bot.get_guild(613747262291443742).get_role(706794165094187038)
        channel = self.bot.get_channel(706810474326655026)
        permission = discord.Permissions(view_channel=True)
        #overwrites = {}
        for user in role.members:
            #overwrites[user] = discord.PermissionOverwrite(view_channel=True)    
            await channel.set_permissions(user,view_channel=True)
            await asyncio.sleep(0.5)
        await ctx.message.add_reaction('✅')

    @commands.command()
    @commands.is_owner()
    async def sqltest(self,ctx):
        self.sqldb.user_setup(ctx.author.id)
        print('done')

    @commands.command()
    @commands.is_owner()
    async def sqltest2(self,ctx):
        user = self.sqldb.get_user(ctx.author.id)
        print(user)

def setup(bot):
    bot.add_cog(debug(bot))