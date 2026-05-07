from pydantic import AliasPath, BaseModel, ConfigDict, Field, model_validator

from v2_starlib.base import UTCDateTime
from v2_starlib.database.postgresql.enums import McssServerStatues

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
    originTime: UTCDateTime = Field(validation_alias=AliasPath("EarthquakeInfo", "OriginTime"))
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

    @property
    def is_significant(self):
        return self.earthquakeNo[3:] != "000"


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


class Coordinate(BaseModel):
    CoordinateName: str
    CoordinateFormat: str
    StationLatitude: float
    StationLongitude: float


class ObsTime(BaseModel):
    DateTime: UTCDateTime


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
    startTime: UTCDateTime
    endTime: UTCDateTime


class DatasetInfo(BaseModel):
    datasetDescription: str
    datasetLanguage: str
    validTime: ValidTime
    issueTime: UTCDateTime
    update: UTCDateTime


class WeatherWarningReport(BaseModel):
    """天氣特報-各別天氣警特報之內容及所影響之區域"""

    datasetInfo: DatasetInfo
    contents: Contents
    hazardConditions: HazardConditions | None = None


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
    updated: UTCDateTime
    updated_parsed: list[int]
    authors: list[TyphoonWarningAuthor]
    author_detail: TyphoonWarningAuthor
    author: str
    links: list[TyphoonWarningLink]
    summary: str
    summary_detail: TyphoonWarningSummaryDetail
    tags: list[TyphoonWarningTag]


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
    creation_date: UTCDateTime = Field(alias="creationDate")
    is_set_to_auto_start: bool = Field(alias="isSetToAutoStart")
    force_save_on_stop: bool = Field(alias="forceSaveOnStop")
    keep_online: int = Field(alias="keepOnline")
    java_allocated_memory: int = Field(alias="javaAllocatedMemory")
    java_startup_line: str = Field(alias="javaStartupLine")

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
