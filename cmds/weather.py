import discord
from discord.ext import commands
import requests

from library import BRS
from core.classes import Cog_Extension
from BotLib.basic import Database

class EarthquakeReport:
    def __init__(self,data):
        self.data = data
        self.earthquakeNo = data['earthquakeNo']
        self.reportImageURI = data['reportImageURI']
        self.originTime = data['earthquakeInfo']['originTime']
        self.depth = data['earthquakeInfo']['depth']['value']
        self.location = data['earthquakeInfo']['epiCenter']['location']
        self.magnitude = data['earthquakeInfo']['magnitude']['magnitudeValue']
        self.reportColor = data['reportColor']
        self.desplay = self.embed()

    def embed(self):
        embed = BRS.simple(f'編號第{self.earthquakeNo}號地震報告')
        embed.add_field(name='發生時間',value=self.originTime)
        embed.add_field(name='震央',value=self.location)
        embed.add_field(name='震源深度',value=f'{self.depth} km')
        embed.add_field(name='芮氏規模',value=f'{self.magnitude}')
        embed.set_image(url=self.reportImageURI)
        return embed
    
    @staticmethod
    def get_report():
        APIdata = requests.get(f'https://opendata.cwb.gov.tw/api/v1/rest/datastore/E-A0015-001?Authorization={Database().CWB_API}&limit=1').json().get('records').get('earthquake')
        if APIdata:
            return EarthquakeReport(APIdata[0])
        else:
            return None
        
    @staticmethod
    def get_report_auto(time):
        APIdata = requests.get(f'https://opendata.cwb.gov.tw/api/v1/rest/datastore/E-A0015-001?Authorization={Database().CWB_API}&timeFrom={time}').json().get('records').get('earthquake')
        if APIdata:
            return EarthquakeReport(APIdata[0])
        else:
            return None
        

class Covid19Report:
    def __init__(self,data):
        self.date = data['a04']
        self.diagnosed_total = data['a05']
        self.diagnosed_new = data['a06']
        self.death_total = data['a08']
        self.death_new = data['a09']
        self.desplay = self.embed()

    def embed(self):
        embed = BRS.simple(f'{self.date} 台灣COVUD-19疫情')
        embed.add_field(name='新增確診',value=self.diagnosed_new)
        embed.add_field(name='總確診數',value=self.diagnosed_total)
        embed.add_field(name='新增死亡',value=self.death_new)
        embed.add_field(name='總死亡數',value=self.death_total)
        #embed.set_image(url=data.reportImageURI)
        return embed

    @staticmethod
    def get_covid19():
        APIdata = requests.get(f'https://covid-19.nchc.org.tw/api/covid19?CK=covid-19@nchc.org.tw&querydata=4001&limited=TWN').json()[0]
        if APIdata:
            return Covid19Report(APIdata)
        else:
            return None

class weather(Cog_Extension):
    @commands.cooldown(rate=1,per=20)
    @commands.command()
    async def earthquake(self,ctx):
        msg = await ctx.send('資料查詢中...')
        embed = EarthquakeReport.get_report().desplay
        if embed:
            await msg.edit(content='查詢成功',embed=embed)
        else:
            await msg.edit(content='查詢失敗',delete_after=5)
    
    @commands.cooldown(rate=1,per=15)
    @commands.command()
    async def covid(self,ctx):
        msg = await ctx.send('資料查詢中...')
        embed = Covid19Report.get_covid19().desplay
        if embed:
            await msg.edit(content='查詢成功',embed=embed)
        else:
            await msg.edit(content='查詢失敗',delete_after=5)

def setup(bot):
    bot.add_cog(weather(bot))