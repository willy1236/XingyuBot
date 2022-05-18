from discord.ext import commands
from core.classes import Cog_Extension
from BotLib.user import *
from BotLib.database import Database


class user_set(Cog_Extension):
    @commands.command()
    async def ui(self,ctx,user=None):
        user_dc = await find.user(ctx,user) or ctx.author
        user = User(user_dc.id)
        embed = user.desplay
        await ctx.send(embed=embed)

def setup(bot):
    bot.add_cog(user_set(bot))