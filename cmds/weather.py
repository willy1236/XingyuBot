from discord.ext import commands

from core.classes import Cog_Extension
from BotLib.interface.weather import *

class weather(Cog_Extension):
    @commands.cooldown(rate=1,per=20)
    @commands.slash_command(description='查詢地震報告')
    async def earthquake(self,ctx):
        embed = EarthquakeReport.get_report().desplay()
        if embed:
            await ctx.respond('查詢成功',embed=embed)
        else:
            await ctx.respond('查詢失敗',delete_after=5)
    
    @commands.cooldown(rate=1,per=15)
    @commands.slash_command(description='查詢疫情資訊')
    async def covid(self,ctx):
        embed = Covid19Report.get_covid19().desplay()
        if embed:
            await ctx.respond('查詢成功',embed=embed)
        else:
            await ctx.respond('查詢失敗',delete_after=5)
    
    @commands.cooldown(rate=1,per=15)
    @commands.slash_command(description='查詢天氣預報')
    async def forecast(self,ctx):
        embed = Forecast.get_report().desplay()
        if embed:
            await ctx.respond('查詢成功',embed=embed)
        else:
            await ctx.respond('查詢失敗',delete_after=5)
def setup(bot):
    bot.add_cog(weather(bot))