import requests

from ..fileDatabase import Jsondb
from ..models.weather import *


def sort_earthquakeReport(x:EarthquakeReport):
    return x.originTime

class CWA_API():
    BaseURL = 'https://opendata.cwa.gov.tw/api/v1/rest/datastore'

    def __init__(self):
        self.auth = Jsondb.get_token('cwa_api')

    def get_earthquake_report(self,significant=True):
        params = {
            'Authorization': self.auth,
            'limit': 1
        }

        id = "E-A0015-001" if significant else "E-A0016-001"
        APIdata = requests.get(f'{self.BaseURL}/{id}',params=params).json().get('records').get('Earthquake')[0]
        
        if APIdata:
            return EarthquakeReport(**APIdata)
        else:
            return None

    def get_earthquake_report_auto(self,timeFrom:str=None, only_significant=False)-> list[EarthquakeReport]:
        params = {
            'Authorization': self.auth,
            'timeFrom': timeFrom
        }
        records = list()

        APIdata = requests.get(f'{self.BaseURL}/E-A0015-001', params=params, timeout=20)
        data = APIdata.json().get('records').get('Earthquake')
        if data:
            records += [EarthquakeReport(**i) for i in data]

        if not only_significant:
            APIdata = requests.get(f'{self.BaseURL}/E-A0016-001', params=params, timeout=20)
            data = APIdata.json().get('records').get('Earthquake')
            if data:
                records += [EarthquakeReport(**i) for i in data]
            
            records.sort(key=sort_earthquakeReport)
        return records

    def get_forecast(self):
        params = {
            'Authorization': self.auth
        }
        APIdata = requests.get(f'{self.BaseURL}/F-C0032-001',params=params).json()
        if APIdata:
            return Forecast(APIdata)
        else:
            return None
        
    def get_weather_warning(self):
        params = {
            'Authorization': self.auth
        }
        APIdata = requests.get(f'{self.BaseURL}/W-C0033-002',params=params).json().get('records').get('record')
        if APIdata:
            return [WeatherWarningReport(**i) for i in APIdata]
        else:
            return None
        
    def get_weather_data(self, StationId="C0Z100"):
        """取得無人氣象站氣象資料"""
        params = {
            'Authorization': self.auth,
            "StationId": StationId
        }
        APIdata = requests.get(f'{self.BaseURL}/O-A0001-001',params=params).json().get('records').get('Station')
        
        if APIdata:
            return [WeatherReport(**i) for i in APIdata]
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