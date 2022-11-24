from discord.ext import commands

from core.classes import Cog_Extension
from BotLib.weatherlib import *

class weather(Cog_Extension):
    @commands.cooldown(rate=1,per=20)
    @commands.command()
    async def earthquake(self,ctx):
        msg = await ctx.send('資料查詢中...')
        embed = EarthquakeReport.get_report().desplay()
        if embed:
            await msg.edit(content='查詢成功',embed=embed)
        else:
            await msg.edit(content='查詢失敗',delete_after=5)
    
    @commands.cooldown(rate=1,per=15)
    @commands.command(enable=True)
    async def covid(self,ctx):
        msg = await ctx.send('資料查詢中...')
        embed = Covid19Report.get_covid19().desplay()
        if embed:
            await msg.edit(content='查詢成功',embed=embed)
        else:
            await msg.edit(content='查詢失敗',delete_after=5)
    
    @commands.cooldown(rate=1,per=15)
    @commands.command(enable=True)
    async def forecast(self,ctx):
        msg = await ctx.send('資料查詢中...')
        embed = Forecast.get_report().desplay()
        if embed:
            await msg.edit(content='查詢成功',embed=embed)
        else:
            await msg.edit(content='查詢失敗',delete_after=5)
def setup(bot):
    bot.add_cog(weather(bot))