from datetime import datetime

import discord
from pydantic import AliasChoices, AliasPath, BaseModel, ConfigDict, Field, model_validator

from starlib.base.types import UTCDateTime
from starlib.database.postgresql.enums import McsmInstanceStatus, McssServerStatues
from starlib.utils import BotEmbed
from starlib.utils.time import convert_tz, nowtz

weather_warning_emojis = {
    "大雨特報": "🌧️",
    "解除大雨特報": "🌧️",
    "颱風警報": "🌀",
    "海上陸上颱風警報": "🌀",
    "海上颱風警報": "🌀",
    "解除颱風警報": "🌀",
    "濃霧特報": "🌫️",
    "解除濃霧特報": "🌫️",
    "豪雨特報": "⛈️",
    "解除豪雨特報": "⛈️",
    "陸上強風特報": "💨",
    "解除陸上強風特報": "💨",
}


class EarthquakeReport(BaseModel):
    """地震報告"""

    model_config = ConfigDict(extra="ignore")

    earthquakeNo: str = Field(validation_alias=AliasPath("EarthquakeNo"), strict=False)
    reportImageURI: str = Field(validation_alias=AliasPath("ReportImageURI"))
    web: str = Field(validation_alias=AliasPath("Web"))
    originTime: datetime = Field(validation_alias=AliasPath("EarthquakeInfo", "OriginTime"))
    depth: float = Field(validation_alias=AliasPath("EarthquakeInfo", "FocalDepth"))
    location: str = Field(validation_alias=AliasPath("EarthquakeInfo", "Epicenter", "Location"))
    magnitude: float = Field(validation_alias=AliasPath("EarthquakeInfo", "EarthquakeMagnitude", "MagnitudeValue"))
    reportColor: str = Field(validation_alias=AliasPath("ReportColor"))
    reportContent: str = Field(validation_alias=AliasPath("ReportContent"))
    intensity: dict = Field(validation_alias=AliasPath("intensity_dict"))

    @model_validator(mode="before")
    @classmethod
    def extract_intensity_info(cls, data: dict):
        data["EarthquakeNo"] = str(data["EarthquakeNo"])
        dct = {}
        for d in data["Intensity"]["ShakingArea"]:
            if d["AreaDesc"].startswith("最大震度"):
                dct[d["AreaDesc"]] = d["CountyName"]
        data["intensity_dict"] = dct
        return data

    @model_validator(mode="after")
    def __post_init__(self):
        self.originTime = convert_tz(self.originTime)
        return self

    @property
    def is_significant(self):
        return self.earthquakeNo[3:] != "000"

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

        embed = discord.Embed(title="地震報告", description=self.reportContent, color=color, url=self.web)

        if self.is_significant:
            embed.add_field(name="地震編號", value=f"{self.earthquakeNo}")
        else:
            embed.add_field(name="地震編號", value=f"{self.earthquakeNo}（小規模）")
        embed.add_field(name="發生時間", value=self.originTime.strftime("%Y/%m/%d %H:%M:%S"))
        embed.add_field(name="震源深度", value=f"{self.depth} km")
        embed.add_field(name="芮氏規模", value=f"{self.magnitude}")
        embed.add_field(name="震央", value=self.location, inline=False)
        if self.intensity and self.earthquakeNo[3:] != "000":
            for key, value in sorted(self.intensity.items(), key=lambda x: x[0], reverse=True):
                embed.add_field(name=key, value=value, inline=False)
        embed.set_image(url=self.reportImageURI)
        embed.set_footer(text="中央氣象暑")
        embed.timestamp = self.originTime
        return embed


class Covid19Report:
    def __init__(self, data):
        self.time = data["time"]
        self.total = data["total"]
        self.new = data["new"]
        self.local = data["local"]
        self.outside = data["outside"]
        self.dead = data["dead"]

    def desplay(self):
        embed = BotEmbed.simple(f"台灣COVUD-19疫情")
        embed.add_field(name="新增確診", value=self.new)
        embed.add_field(name="本土病例", value=self.local)
        embed.add_field(name="境外移入", value=self.outside)
        embed.add_field(name="總確診數", value=self.total)
        embed.add_field(name="新增死亡", value=self.dead)
        embed.set_footer(text=self.time)
        return embed


class Forecast:
    def __init__(self, data):
        all_data = data["records"]["location"]
        self.forecast_all = []
        self.timestart = all_data[0]["weatherElement"][4]["time"][0]["startTime"]
        self.timeend = all_data[0]["weatherElement"][4]["time"][0]["endTime"]
        for pos in all_data:
            name = pos["locationName"]
            Wx = pos["weatherElement"][0]["time"][0]["parameter"]["parameterName"]
            minT = pos["weatherElement"][2]["time"][0]["parameter"]["parameterName"]
            Cl = pos["weatherElement"][3]["time"][0]["parameter"]["parameterName"]
            maxT = pos["weatherElement"][4]["time"][0]["parameter"]["parameterName"]

            forecast_one = {"name": name, "Wx": Wx, "minT": minT, "Cl": Cl, "maxT": maxT}
            self.forecast_all.append(forecast_one)

    def embed(self):
        embed = BotEmbed.general("天氣預報")
        for data in self.forecast_all:
            text = f"{data['Wx']}\n高低溫:{data['maxT']}/{data['minT']}\n{data['Cl']}"
            embed.add_field(name=data["name"], value=text)
        embed.timestamp = datetime.now()
        embed.set_footer(text=f"{self.timestart}至{self.timeend}")
        return embed


class Coordinate(BaseModel):
    CoordinateName: str
    CoordinateFormat: str
    StationLatitude: float
    StationLongitude: float


class ObsTime(BaseModel):
    DateTime: datetime


class GeoInfo(BaseModel):
    Coordinates: list[Coordinate]
    StationAltitude: str
    CountyName: str
    TownName: str
    CountyCode: str
    TownCode: str


class GustInfo(BaseModel):
    PeakGustSpeed: float
    Occurred_at: dict | None


class TemperatureInfo(BaseModel):
    AirTemperature: float | None = None
    Occurred_at: ObsTime | None = None


class DailyExtreme(BaseModel):
    DailyHigh: TemperatureInfo
    DailyLow: TemperatureInfo


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
    location: list[AffectedArea]


class HazardInfo(BaseModel):
    language: str
    phenomena: str
    significance: str
    affectedAreas: Locations


class Hazard(BaseModel):
    info: HazardInfo


class Hazards(BaseModel):
    hazard: list[Hazard]


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
    issueTime: UTCDateTime
    update: datetime


class WeatherWarningReport(BaseModel):
    """天氣特報-各別天氣警特報之內容及所影響之區域"""

    datasetInfo: DatasetInfo
    contents: Contents
    hazardConditions: HazardConditions | None = None

    @model_validator(mode="after")
    def __post_init__(self):
        self.datasetInfo.issueTime = convert_tz(self.datasetInfo.issueTime)
        self.datasetInfo.validTime.startTime = convert_tz(self.datasetInfo.validTime.startTime)
        self.datasetInfo.validTime.endTime = convert_tz(self.datasetInfo.validTime.endTime)
        self.datasetInfo.update = convert_tz(self.datasetInfo.update)
        return self

    def embed(self):
        emoji = weather_warning_emojis.get(self.datasetInfo.datasetDescription, "🚨")
        embed = BotEmbed.general("天氣警特報", title=f"{emoji}{self.datasetInfo.datasetDescription}", description=f"**{self.contents.content.contentText[1:]}**")
        embed.add_field(name="發布時間", value=self.datasetInfo.issueTime.strftime("%Y/%m/%d %H:%M"))
        embed.add_field(name="開始時間", value=self.datasetInfo.validTime.startTime.strftime("%Y/%m/%d %H:%M"))
        embed.add_field(name="結束時間", value=self.datasetInfo.validTime.endTime.strftime("%Y/%m/%d %H:%M"))
        if self.hazardConditions:
            embed.add_field(name="涵蓋區域市", value=", ".join([i.locationName for i in self.hazardConditions.hazards.hazard[0].info.affectedAreas.location]))

        embed.timestamp = nowtz()
        embed.set_footer(text=f"中央氣象暑")
        return embed


class TyphoonWarningAuthor(BaseModel):
    name: str


class TyphoonWarningLink(BaseModel):
    rel: str
    href: str
    type: str


class TyphoonWarningTag(BaseModel):
    term: str
    scheme: str | None = None
    label: str | None = None


class TyphoonWarningTitleDetail(BaseModel):
    type: str
    language: str | None = None
    base: str
    value: str


class TyphoonWarningSummaryDetail(BaseModel):
    type: str
    language: str | None = None
    base: str
    value: str


class TyphoonWarningReport(BaseModel):
    id: str
    guidislink: bool
    link: str
    title: str
    title_detail: TyphoonWarningTitleDetail
    updated: datetime
    updated_parsed: list[int]
    authors: list[TyphoonWarningAuthor]
    author_detail: TyphoonWarningAuthor
    author: str
    links: list[TyphoonWarningLink]
    summary: str
    summary_detail: TyphoonWarningSummaryDetail
    tags: list[TyphoonWarningTag]

    def embed(self):
        embed = BotEmbed.general("颱風警報", title=self.title, description=self.summary.replace("＊", "\n- "))
        embed.add_field(name="發布時間", value=self.updated.strftime("%Y/%m/%d %H:%M"))
        embed.timestamp = self.updated
        embed.set_footer(text="NCDR")
        return embed


mcss_server_status = {
    0: "離線",
    1: "啟動",
    2: "停止",
}


class McssServer(BaseModel):
    """MCSS 伺服器設定模型"""

    server_id: str = Field(alias="serverId")
    status: McssServerStatues
    name: str
    description: str
    path_to_folder: str = Field(alias="pathToFolder")
    folder_name: str = Field(alias="folderName")
    type: str
    creation_date: datetime = Field(alias="creationDate")
    is_set_to_auto_start: bool = Field(alias="isSetToAutoStart")
    force_save_on_stop: bool = Field(alias="forceSaveOnStop")
    keep_online: int = Field(alias="keepOnline")
    java_allocated_memory: int = Field(alias="javaAllocatedMemory")
    java_startup_line: str = Field(alias="javaStartupLine")

    def embed(self):
        embed = BotEmbed.simple(self.name, self.description)
        embed.add_field(name="Minecraft類型", value=self.type)
        embed.add_field(name="伺服器狀態", value=f"{self.status.value}（{str(self.status)}）")
        embed.add_field(name="創建日期", value=self.creation_date.strftime("%Y-%m-%d %H:%M:%S"))
        embed.add_field(name="記憶體分配", value=f"{self.java_allocated_memory} MB")
        embed.set_footer(text=f"伺服器ID：{self.server_id}")
        return embed

    def find_port(self):
        parts = self.name.split()
        if self.description is not None:
            parts += self.description.split()
        for part in parts:
            if part.isdigit():
                num = int(part)
                if 25565 <= num <= 65535:
                    return num
        return None


class McsmInstance(BaseModel):
    """MCSManager 伺服器實例模型（欄位對照真實 `GET /api/instance` 回應確認）"""

    model_config = ConfigDict(extra="ignore")

    server_id: str = Field(validation_alias=AliasChoices("uuid", "instanceUuid"))
    daemon_id: str = Field(alias="daemonId")
    status: McsmInstanceStatus
    name: str
    port: int | None = None

    @model_validator(mode="before")
    @classmethod
    def extract_config_fields(cls, data: dict):
        config = data.get("config") or {}
        data.setdefault("name", config.get("nickname"))
        data.setdefault("port", (config.get("pingConfig") or {}).get("port"))
        return data

    def embed(self):
        embed = BotEmbed.simple(self.name)
        embed.add_field(name="伺服器狀態", value=f"{self.status.value}（{str(self.status)}）")
        if self.port:
            embed.add_field(name="端口", value=str(self.port))
        embed.set_footer(text=f"伺服器ID：{self.server_id}")
        return embed

    def find_port(self):
        return self.port
