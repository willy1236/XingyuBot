import datetime,discord

from bothelper import BotEmbed


class EarthquakeReport():
    def __init__(self,data,auto_type=None):
        self.data = data
        self.auto_type = auto_type
        self.earthquakeNo = str(data['EarthquakeNo'])
        self.reportImageURI = data['ReportImageURI']
        self.web = data['Web']
        self.originTime = data['EarthquakeInfo']['OriginTime']
        self.depth = data['EarthquakeInfo']['FocalDepth']
        self.location = data['EarthquakeInfo']['Epicenter']['Location']
        self.magnitude = data['EarthquakeInfo']['EarthquakeMagnitude']['MagnitudeValue']
        self.reportColor = data['ReportColor']
        self.reportContent = data['ReportContent']

    def desplay(self):
        if self.reportColor == "綠色":
            embed = discord.Embed(description=self.reportContent,color=0x00BB00)
        elif self.reportColor == "橙色":
            embed = discord.Embed(description=self.reportContent,color=0xF75000)
        elif self.reportColor == "黃色":
            embed = discord.Embed(description=self.reportContent,color=0xFFFF37)
        else:
            embed = discord.Embed(description=self.reportContent,color=0xEA0000)
        
        if self.earthquakeNo[3:] == "000":
            embed.add_field(name='地震編號',value=f'{self.earthquakeNo}（小規模）')
        else:
            embed.add_field(name='地震編號',value=f'{self.earthquakeNo}')
        embed.add_field(name='發生時間',value=self.originTime)
        embed.add_field(name='震源深度',value=f'{self.depth} km')
        embed.add_field(name='芮氏規模',value=f'{self.magnitude}')
        embed.add_field(name='震央',value=self.location,inline=False)
        embed.set_image(url=self.reportImageURI)
        return embed
        

class Covid19Report():
    def __init__(self,data):
        self.time = data['time']
        self.total = data['total']
        self.new = data['new']
        self.local = data['local']
        self.outside = data['outside']
        self.dead =data['dead']

    def desplay(self):
        embed = BotEmbed.simple(f'台灣COVUD-19疫情')
        embed.add_field(name='新增確診',value=self.new)
        embed.add_field(name='本土病例',value=self.local)
        embed.add_field(name='境外移入',value=self.outside)
        embed.add_field(name='總確診數',value=self.total)
        embed.add_field(name='新增死亡',value=self.dead)
        embed.set_footer(text=self.time)
        return embed

class Forecast():
    def __init__(self,data):
        all_data = data['records']['location']
        self.forecast_all = []
        self.timestart = all_data[0]['weatherElement'][4]['time'][0]['startTime']
        self.timeend = all_data[0]['weatherElement'][4]['time'][0]['endTime']
        for pos in all_data:
            name = pos['locationName']
            Wx = pos['weatherElement'][0]['time'][0]['parameter']['parameterName']
            minT = pos['weatherElement'][2]['time'][0]['parameter']['parameterName']
            Cl = pos['weatherElement'][3]['time'][0]['parameter']['parameterName']
            maxT = pos['weatherElement'][4]['time'][0]['parameter']['parameterName']
            
            forecast_one = {
                "name":name,
                "Wx":Wx,
                "minT":minT,
                "Cl":Cl,
                "maxT":maxT
            }
            self.forecast_all.append(forecast_one)

    def desplay(self):
        embed = BotEmbed.general('天氣預報')
        for data in self.forecast_all:
            text = f"{data['Wx']}\n高低溫:{data['maxT']}/{data['minT']}\n{data['Cl']}"
            embed.add_field(name=data['name'],value=text)
        embed.timestamp = datetime.datetime.now()
        embed.set_footer(text=f'時間為{self.timestart}至{self.timeend}')
        return embed