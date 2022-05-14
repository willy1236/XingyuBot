import discord,json,requests
from discord.ext import commands
from core.classes import Cog_Extension
from library import *

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
    rsdata = Database().rsdata
    
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
    async def test(self, ctx,*arg):
        print(arg,type(arg))
    
    @commands.command()
    @commands.is_owner()
    async def prepare(self,ctx: commands.Context):
        """Starts a persistent view."""
        # In order for a persistent view to be listened to, it needs to be sent to an actual message.
        # Call this method once just to store it somewhere.
        # In a more complicated program you might fetch the message_id from a database for use later.
        # However this is outside of the scope of this simple example.
        await ctx.send("What's your favourite colour?", view=PersistentView())


    
    # @commands.command(enabled=False)
    # async def test(self,ctx,user=None):
    #     user = await find.user(ctx,user)
    #     await ctx.send(f"{user or '沒有找到用戶'}")
def setup(bot):
    bot.add_cog(debug(bot))