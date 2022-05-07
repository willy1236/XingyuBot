import discord
from discord.ext import commands
import json ,requests

from library import BRS
from core.classes import Cog_Extension
from BotLib.basic import Database

class EarthquakeReport:
    def __init__(self,data):
        self.data = data
        self.earthquakeNo = data['earthquake'][0]['earthquakeNo']
        self.reportImageURI = data['earthquake'][0]['reportImageURI']
        self.originTime = data['earthquake'][0]['earthquakeInfo']['originTime']
        self.depth = data['earthquake'][0]['earthquakeInfo']['depth']['value']
        self.location = data['earthquake'][0]['earthquakeInfo']['epiCenter']['location']
        self.magnitude = data['earthquake'][0]['earthquakeInfo']['magnitude']['magnitudeValue']
        self.reportColor = data['earthquake'][0]['reportColor']

class Covid19Report:
    def __init__(self,data):
        self.date = data['a04']
        self.diagnosed_total = data['a05']
        self.diagnosed_new = data['a06']
        self.death_total = data['a08']
        self.death_new = data['a09']

        
class weather(Cog_Extension):
    @commands.cooldown(rate=1,per=20)
    @commands.command()
    async def earthquake(self,ctx):
        msg = await ctx.send('資料查詢中...')
        APIdata = requests.get(f'https://opendata.cwb.gov.tw/api/v1/rest/datastore/E-A0015-001?Authorization={Database().CWB_API}&limit=1&format=JSON').json().get('records')
        data = EarthquakeReport(APIdata)
        
        embed = BRS.simple(f'編號第{data.earthquakeNo}號地震報告')
        embed.add_field(name='發生時間',value=data.originTime)
        embed.add_field(name='震央',value=data.location)
        embed.add_field(name='震源深度',value=f'{data.depth} km')
        embed.add_field(name='芮氏規模',value=f'{data.magnitude}')
        embed.set_image(url=data.reportImageURI)
        await msg.edit(content='查詢成功',embed=embed)

    @commands.cooldown(rate=1,per=15)
    @commands.command()
    async def covid(self,ctx):
        msg = await ctx.send('資料查詢中...')
        r = requests.get(f'https://covid-19.nchc.org.tw/api/covid19?CK=covid-19@nchc.org.tw&querydata=4001&limited=TWN').json()
        APIdata = r[0]
        data = Covid19Report(APIdata)
        
        embed = BRS.simple(f'{data.date} 台灣COVUD-19疫情')
        embed.add_field(name='新增確診',value=data.diagnosed_new)
        embed.add_field(name='總確診數',value=data.diagnosed_total)
        embed.add_field(name='新增死亡',value=data.death_new)
        embed.add_field(name='總死亡數',value=data.death_total)
        #embed.set_image(url=data.reportImageURI)
        await msg.edit(content='查詢成功',embed=embed)

def setup(bot):
    bot.add_cog(weather(bot))