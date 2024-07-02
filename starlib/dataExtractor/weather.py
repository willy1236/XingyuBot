import requests,time
from bs4 import BeautifulSoup

from starlib.fileDatabase import Jsondb
from starlib.models.weather import *

class WeatherClient():
    """天氣資料交互"""

class CWA_API(WeatherClient):
    def __init__(self):
        super().__init__()
        self.auth = Jsondb.get_token('cwa_api')
        self.url = 'https://opendata.cwa.gov.tw/api/v1/rest/datastore'

    def get_earthquake_report(self,significant=True):
        params = {
            'Authorization': self.auth,
            'limit': 1
        }

        id = "E-A0015-001" if significant else "E-A0016-001"        
        APIdata = requests.get(f'{self.url}/{id}',params=params).json().get('records').get('Earthquake')[0]
        
        if APIdata:
            return EarthquakeReport(APIdata)
        else:
            return None

    def get_earthquake_report_auto(self,timeFrom=None):
        params = {
            'Authorization': self.auth,
            'timeFrom': timeFrom,
            'limit': 5
        }
        APIdata = requests.get(f'{self.url}/E-A0015-001',params=params,timeout=20)
        data = APIdata.json().get('records').get('Earthquake')
        if data:
            return [EarthquakeReport(i,auto_type='E-A0015-001') for i in data]
        else:
            time.sleep(1)
            APIdata = requests.get(f'{self.url}/E-A0016-001',params=params,timeout=20)
            data = APIdata.json().get('records').get('Earthquake')
            if data:
                return [EarthquakeReport(i,auto_type='E-A0016-001') for i in data]
            else:
                return None

    def get_forecast(self):
        params = {
            'Authorization': self.auth
        }
        APIdata = requests.get(f'{self.url}/F-C0032-001',params=params).json()
        if APIdata:
            return Forecast(APIdata)
        else:
            return None
        
    def get_weather_warning(self):
        params = {
            'Authorization': self.auth,
            'limit': 1
        }
        APIdata = requests.get(f'{self.url}/W-C0033-002',params=params).json().get('records').get('record')
        if APIdata:
            return [WeatherWarning(i) for i in APIdata]
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