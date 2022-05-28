from discord.ext import commands
from core.classes import Cog_Extension
from BotLib.user import *
from BotLib.database import Database
from library import find

class user_system(Cog_Extension):
    @commands.command()
    async def ui(self,ctx,user=None):
        user_dc = await find.user(ctx,user) or ctx.author
        user = User(user_dc.id,user_dc.name)
        await ctx.send(embed=user.desplay)

def setup(bot):
    bot.add_cog(user_system(bot))