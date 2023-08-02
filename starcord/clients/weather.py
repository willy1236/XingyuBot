import requests,time
from bs4 import BeautifulSoup

from starcord.database import Jsondb
from starcord.model.weather import *

class WeatherClient():
    """天氣資料交互"""

class CWBClient(WeatherClient):
    def __init__(self):
        super().__init__()
        self.auth = Jsondb.get_token('CWB_api')
        self.url = 'https://opendata.cwb.gov.tw/api/v1/rest/datastore'

    def get_earthquake_report(self,significant=False):
        params = {
            'Authorization': self.auth,
            'limit': 1
        }
        if significant:
            APIdata = requests.get(f'{self.url}/E-A0015-001',params=params).json().get('records').get('Earthquake')[0]
        else:
            APIdata = requests.get(f'{self.url}/E-A0016-001',params=params).json().get('records').get('Earthquake')[0]
        
        if APIdata:
            return EarthquakeReport(APIdata)
        else:
            return None

    def get_earthquake_report_auto(self,timeFrom=None):
        params = {
            'Authorization': self.auth,
            'timeFrom': timeFrom,
            'limit': 1
        }
        APIdata = requests.get(f'{self.url}/E-A0015-001',params=params,timeout=20)
        data = APIdata.json().get('records').get('Earthquake')
        if data:
            return EarthquakeReport(data[0],auto_type='E-A0015-001')
        else:
            time.sleep(1)
            APIdata = requests.get(f'{self.url}/E-A0016-001',params=params,timeout=20)
            data = APIdata.json().get('records').get('Earthquake')
            if data:
                return EarthquakeReport(data[0],auto_type='E-A0016-001')
            else:
                return None

    def get_forecast(self):
        params = {
            'Authorization': self.auth
        }
        APIdata = requests.get(f'{self.url}/F-C0032-001?Authorization={self.auth}',params=params).json()
        if APIdata:
            return Forecast(APIdata)
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