from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional

import discord

from ..utilities import BotEmbed

class EarthquakeReport():
    def __init__(self,data,auto_type=None):
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
        self.intensity = {}
        for data in data.get("Intensity").get("ShakingArea"):
            if data["AreaDesc"].startswith("最大震度"):
                self.intensity[data['AreaDesc']] = data['CountyName']

    def embed(self):
        match self.reportColor:
            case "綠色":
                color = 0x00BB00
            case "橙色":
                color = 0xF75000
            case "黃色":
                color = 0xFFFF37
            case _:
                color = 0xEA0000
        
        embed = discord.Embed(title='地震報告',description=self.reportContent,color=color,url=self.web)
        
        if self.earthquakeNo[3:] == "000":
            embed.add_field(name='地震編號',value=f'{self.earthquakeNo}（小規模）')
        else:
            embed.add_field(name='地震編號',value=f'{self.earthquakeNo}')
        embed.add_field(name='發生時間',value=self.originTime)
        embed.add_field(name='震源深度',value=f'{self.depth} km')
        embed.add_field(name='芮氏規模',value=f'{self.magnitude}')
        embed.add_field(name='震央',value=self.location,inline=False)
        if self.intensity and self.earthquakeNo[3:] != "000":
            for key, value in sorted(self.intensity.items(), key=lambda x:x[0]):
                embed.add_field(name=key,value=value,inline=False)
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
        embed.timestamp = datetime.now()
        embed.set_footer(text=f'{self.timestart}至{self.timeend}')
        return embed

class Coordinate(BaseModel):
    CoordinateName: str
    CoordinateFormat: str
    StationLatitude: float
    StationLongitude: float

class ObsTime(BaseModel):
    DateTime: datetime

class GeoInfo(BaseModel):
    Coordinates: List[Coordinate]
    StationAltitude: str
    CountyName: str
    TownName: str
    CountyCode: str
    TownCode: str

class GustInfo(BaseModel):
    PeakGustSpeed: float
    Occurred_at: Optional[dict]

class TemperatureInfo(BaseModel):
    AirTemperature: float = None
    Occurred_at: ObsTime = None

class DailyExtreme(BaseModel):
    DailyHigh: TemperatureInfo = None
    DailyLow: TemperatureInfo = None

class WeatherElement(BaseModel):
    Weather: str
    Now: dict
    WindDirection: int
    WindSpeed: float
    AirTemperature: float
    RelativeHumidity: int
    AirPressure: float
    GustInfo: GustInfo
    DailyExtreme: DailyExtreme

class WeatherReport(BaseModel):
    """自動氣象站氣象觀測資料"""
    StationName: str
    StationId: str
    ObsTime: ObsTime
    GeoInfo: GeoInfo
    WeatherElement: WeatherElement

class AffectedArea(BaseModel):
    locationName: str

class Locations(BaseModel):
    location: List[AffectedArea]

class HazardInfo(BaseModel):
    language: str
    phenomena: str
    significance: str
    affectedAreas: Locations

class Hazard(BaseModel):
    info: HazardInfo

class Hazards(BaseModel):
    hazard: List[Hazard]

class HazardConditions(BaseModel):
    hazards: Hazards

class Content(BaseModel):
    contentLanguage: str
    contentText: str

class Contents(BaseModel):
    content: Content

class ValidTime(BaseModel):
    startTime: datetime
    endTime: datetime

class DatasetInfo(BaseModel):
    datasetDescription: str
    datasetLanguage: str
    validTime: ValidTime
    issueTime: datetime
    update: datetime

class WeatherWarningReport(BaseModel):
    """天氣特報-各別天氣警特報之內容及所影響之區域"""
    datasetInfo: DatasetInfo
    contents: Contents
    hazardConditions: HazardConditions | None = None

    def embed(self):
        embed = BotEmbed.general('天氣警特報',title=self.datasetInfo.datasetDescription,description=self.contents.content.contentText)
        embed.add_field(name='發布時間',value=self.datasetInfo.issueTime)
        embed.add_field(name='開始時間',value=self.datasetInfo.validTime.startTime)
        embed.add_field(name='結束時間',value=self.datasetInfo.validTime.endTime)
        if self.hazardConditions:
            embed.add_field(name='涵蓋區域市',value=", ".join([i.locationName for i in self.hazardConditions.hazards.hazard[0].info.affectedAreas.location]))

        embed.timestamp = datetime.now()
        embed.set_footer(text=f'最後更新：{self.datasetInfo.update}')
        return embed