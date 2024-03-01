from discord.ext import commands
from starcord import Cog_Extension
from starcord.DataExtractor.weather import *

class weather(Cog_Extension):
    @commands.cooldown(rate=1,per=20)
    @commands.slash_command(description='查詢最新的顯著地震報告')
    async def earthquake(self,ctx):
        report = CWA_API().get_earthquake_report()
        if report:
            await ctx.respond('查詢成功',embed=report.embed())
        else:
            await ctx.respond('查詢失敗',delete_after=5)

    @commands.cooldown(rate=1,per=15)
    @commands.slash_command(description='查詢12小時天氣預報')
    async def forecast(self,ctx):
        report = CWA_API().get_forecast()
        if report:
            await ctx.respond('查詢成功',embed=report.desplay())
        else:
            await ctx.respond('查詢失敗',delete_after=5)

    @commands.cooldown(rate=1,per=15)
    @commands.slash_command(description='查詢天氣警特報（開發中）')
    async def weatherwarning(self,ctx):
        report = CWA_API().get_weather_warning()
        if report:
            await ctx.respond('查詢成功',embed=report.desplay())
        else:
            await ctx.respond('目前無發布中警特報',delete_after=5)

def setup(bot):
    bot.add_cog(weather(bot))