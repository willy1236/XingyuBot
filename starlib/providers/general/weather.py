import certifi
import feedparser

from starlib.database import APIType, sqldb

from ..base import APICaller
from .models import *


def sort_earthquakeReport(x: EarthquakeReport):
    return x.originTime


class CWA_API(APICaller):
    base_url = "https://opendata.cwa.gov.tw/api/v1/rest/datastore"

    def __init__(self):
        auth = sqldb.get_access_token(APIType.CWA).access_token
        super().__init__(headers={"Authorization": auth})

    def get_earthquake_report(self, significant=True):
        endpoint = "E-A0015-001" if significant else "E-A0016-001"
        r = self.get(endpoint, params={"limit": 1})
        if r is None:
            return None

        data = r.json().get("records", {}).get("Earthquake") or []
        return EarthquakeReport(**data[0]) if data else None

    def get_earthquake_report_auto(self, timeFrom: str = None, only_significant=False) -> list[EarthquakeReport]:
        params = {"timeFrom": timeFrom} if timeFrom else None
        records: list[EarthquakeReport] = []
        endpoints = ["E-A0015-001"] if only_significant else ["E-A0015-001", "E-A0016-001"]

        for endpoint in endpoints:
            r = self.get(endpoint, params=params, timeout=20)
            if r is None:
                continue
            data = r.json().get("records", {}).get("Earthquake") or []
            records.extend(EarthquakeReport(**i) for i in data)

        if not only_significant:
            records.sort(key=sort_earthquakeReport)
        return records

    def get_forecast(self):
        r = self.get("F-C0032-001")
        if r is None:
            return None
        return Forecast(r.json())

    def get_weather_warning(self):
        r = self.get("W-C0033-002")
        if r is None:
            return []
        return [WeatherWarningReport(**i) for i in (r.json().get("records", {}).get("record") or [])]

    def get_weather_data(self, StationId="C0Z100"):
        """取得無人氣象站氣象資料"""
        params = {"StationId": StationId}
        r = self.get("O-A0001-001", params=params)
        if r is None:
            return []
        return [WeatherReport(**i) for i in (r.json().get("records", {}).get("Station") or [])]


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


class NCDRRSS(APICaller):
    base_url = "https://alerts.ncdr.nat.gov.tw"

    def get_typhoon_warning(self, after: datetime | None = None) -> list[TyphoonWarningReport]:
        """從RSS取得颱風警報（由舊到新）"""
        response = self.get("RssAtomFeed.ashx?AlertType=5", verify=certifi.where())

        feed = feedparser.parse(response.content)
        if feed.bozo:
            raise feed.bozo_exception
        datas = [TyphoonWarningReport(**entry) for entry in feed["entries"]]
        if after:
            return [entry for entry in datas if entry.updated > after]
        return datas
