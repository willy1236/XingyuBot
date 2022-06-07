from bs4 import BeautifulSoup
import discord
from discord.ext import commands
import requests

from core.classes import Cog_Extension
from BotLib.database import Database
from BotLib.basic import BotEmbed


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
        embed = BotEmbed.simple(f'編號第{self.earthquakeNo}號地震報告')
        embed.add_field(name='發生時間',value=self.originTime)
        embed.add_field(name='震央',value=self.location)
        embed.add_field(name='震源深度',value=f'{self.depth} km')
        embed.add_field(name='芮氏規模',value=f'{self.magnitude}')
        embed.set_image(url=self.reportImageURI)
        return embed
    
    @staticmethod
    def get_report(significant=False):
        if significant:
            APIdata = requests.get(f'https://opendata.cwb.gov.tw/api/v1/rest/datastore/E-A0015-001?Authorization={Database().CWB_API}&limit=1').json().get('records').get('earthquake')
        else:
            APIdata = requests.get(f'https://opendata.cwb.gov.tw/api/v1/rest/datastore/E-A0016-001?Authorization={Database().CWB_API}&limit=1').json().get('records').get('earthquake')
        if APIdata:
            return EarthquakeReport(APIdata[0])
        else:
            return None
        
    @staticmethod
    def get_report_auto(time):
        APIdata = requests.get(f'https://opendata.cwb.gov.tw/api/v1/rest/datastore/E-A0016-001?Authorization={Database().CWB_API}&timeFrom={time}').json().get('records').get('earthquake')
        if APIdata:
            return EarthquakeReport(APIdata[0])
        else:
            return None
        

class Covid19Report:
    def __init__(self,data):
        self.time = data['time']
        self.total = data['total']
        self.new = data['new']
        self.local = data['local']
        self.outside = data['outside']
        self.dead =data['dead']
        self.desplay = self.embed()

    def embed(self):
        embed = BotEmbed.simple(f'台灣COVUD-19疫情')
        embed.add_field(name='新增確診',value=self.new)
        embed.add_field(name='本土病例',value=self.local)
        embed.add_field(name='境外移入',value=self.outside)
        embed.add_field(name='總確診數',value=self.total)
        embed.add_field(name='新增死亡',value=self.dead)
        embed.set_footer(text=self.time)
        #embed.set_image(url=data.reportImageURI)
        return embed

    # @staticmethod
    # def get_covid19():
    #     APIdata = requests.get(f'https://covid-19.nchc.org.tw/api/covid19?CK=covid-19@nchc.org.tw&querydata=4001&limited=TWN').json()[0]
    #     if APIdata:
    #         return Covid19Report(APIdata)
    #     else:
    #         return None


    @staticmethod
    def get_covid19():
        r = requests.get(f'https://news.campaign.yahoo.com.tw/2019-nCoV/index.php')
        soup = BeautifulSoup(r.text, "html.parser")
        results = soup.find_all("section",class_="secTaiwan")
        r2 = results[0].select_one('div',class_="content").select('div',class_="list")
        r3 = r2[2].dl.select('div')

        dict = {
            "time": r2[1].text,
            "total": r3[1].text,
            "new":r3[3].text,
            "local":r3[5].text,
            "outside":r3[7].text,
            "dead":r3[9].text
        }
        return Covid19Report(dict)

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
    @commands.command(enable=True)
    async def covid(self,ctx):
        msg = await ctx.send('資料查詢中...')
        embed = Covid19Report.get_covid19().desplay
        if embed:
            await msg.edit(content='查詢成功',embed=embed)
        else:
            await msg.edit(content='查詢失敗',delete_after=5)

def setup(bot):
    bot.add_cog(weather(bot))