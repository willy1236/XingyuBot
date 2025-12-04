import requests
import feedparser
import certifi

from ..database import sqldb
from ..models.weather import *
from ..types import APIType


def sort_earthquakeReport(x:EarthquakeReport):
    return x.originTime

class CWA_API():
    BaseURL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore"

    def __init__(self):
        self.auth = sqldb.get_access_token(APIType.CWA).access_token

    def get_earthquake_report(self,significant=True):
        params = {"Authorization": self.auth, "limit": 1}

        id = "E-A0015-001" if significant else "E-A0016-001"
        r = requests.get(f"{self.BaseURL}/{id}", params=params)

        if r.ok:
            data = r.json().get("records").get("Earthquake")[0]
            return EarthquakeReport(**data)
        else:
            return None

    def get_earthquake_report_auto(self,timeFrom:str=None, only_significant=False)-> list[EarthquakeReport]:
        params = {"Authorization": self.auth, "timeFrom": timeFrom}
        records = list()

        r = requests.get(f"{self.BaseURL}/E-A0015-001", params=params, timeout=20)
        r.raise_for_status()
        data = r.json().get("records").get("Earthquake")
        if data:
            records += [EarthquakeReport(**i) for i in data]

        if not only_significant:
            r = requests.get(f"{self.BaseURL}/E-A0016-001", params=params, timeout=20)
            data = r.json().get("records").get("Earthquake")
            if data:
                records += [EarthquakeReport(**i) for i in data]

            records.sort(key=sort_earthquakeReport)
        return records

    def get_forecast(self):
        params = {"Authorization": self.auth}
        r = requests.get(f"{self.BaseURL}/F-C0032-001", params=params)
        if r.ok:
            return Forecast(r.json())
        else:
            return None

    def get_weather_warning(self):
        params = {"Authorization": self.auth}
        r = requests.get(f"{self.BaseURL}/W-C0033-002", params=params)
        if r.ok:
            return [WeatherWarningReport(**i) for i in r.json().get("records").get("record")]
        else:
            return None

    def get_weather_data(self, StationId="C0Z100"):
        """取得無人氣象站氣象資料"""
        params = {"Authorization": self.auth, "StationId": StationId}
        r = requests.get(f"{self.BaseURL}/O-A0001-001", params=params)
        if r.ok:
            return [WeatherReport(**i) for i in r.json().get("records").get("Station")]
        else:
            return None


# class Covid19Client(WeatherClient):
#     def get_covid19():
#         r = requests.get(f'https://news.campaign.yahoo.com.tw/2019-nCoV/index.php')
#         soup = BeautifulSoup(r.text, "html.parser")
#         results = soup.find_all("section",class_="secTaiwan")
#         r2 = results[0].select_one('div',class_="content").select('div',class_="list")
#         r3 = r2[2].dl.select('div')

#         dict = {
#             "time": r2[1].text,
#             "total": r3[1].text,
#             "new":r3[3].text,
#             "local":r3[5].text,
#             "outside":r3[7].text,
#             "dead":r3[9].text
#         }
#         return Covid19Report(dict)

class NCDRRSS:
    def get_typhoon_warning(self, after: datetime | None = None) -> list[TyphoonWarningReport]:
        """從RSS取得颱風警報（由舊到新）"""
        response = requests.get("https://alerts.ncdr.nat.gov.tw/RssAtomFeed.ashx?AlertType=5", verify=certifi.where())
        response.raise_for_status()

        feed = feedparser.parse(response.content)
        if feed.bozo:
            raise feed.bozo_exception
        datas = [TyphoonWarningReport(**entry) for entry in feed["entries"]]
        if after:
            return [entry for entry in datas if entry.updated > after]
        return datas
