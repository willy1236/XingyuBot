import discord
from discord.ext import commands
import json ,requests

from library import BRS
from core.classes import Cog_Extension
from BotLib.basic import Database


r = requests.get('https://opendata.cwb.gov.tw/api/v1/rest/datastore/E-A0015-001?Authorization=CWB-68A93663-BED9-4D7E-9305-E42BC130F02D&limit=1&format=JSON')
data = json.loads(r.text)

class EarthquakeReport:
    def __init__(self,data):
        self.data = data
        self.earthquakeNo = data['records']['earthquake'][0]['earthquakeNo']
        self.reportImageURI = data['records']['earthquake'][0]['reportImageURI']
        self.originTime = data['records']['earthquake'][0]['earthquakeInfo']['originTime']
        self.depth = data['records']['earthquake'][0]['earthquakeInfo']['depth']['value']
        self.location = data['records']['earthquake'][0]['earthquakeInfo']['epiCenter']['location']

        

class weather(Cog_Extension):
    @commands.cooldown(rate=1,per=20)
    @commands.command()
    async def earthquake(self,ctx):
        msg = await ctx.send('資料查詢中...')
        r = requests.get(f'https://opendata.cwb.gov.tw/api/v1/rest/datastore/E-A0015-001?Authorization={Database().CWB_API}&limit=1&format=JSON')
        APIdata = json.loads(r.text)
        data = EarthquakeReport(APIdata)
        
        embed = BRS.simple(f'編號第{data.earthquakeNo}號地震報告')
        embed.add_field(name='發生時間',value=data.originTime)
        embed.add_field(name='震央',value=data.location)
        embed.add_field(name='震源深度',value=f'{data.depth} km')
        embed.set_image(url=data.reportImageURI)
        await msg.edit(content='查詢成功',embed=embed)

def setup(bot):
    bot.add_cog(weather(bot))