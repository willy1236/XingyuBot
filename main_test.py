import requests
import xml.etree.ElementTree as ET
import bothelper
from bothelper.interface.weather import EarthquakeReport

Jsondb = bothelper.Jsondb

# id ='UCgJR1i4QQ7O3yyrFROP_HvQ'
# url = f"https://www.youtube.com/feeds/videos.xml?channel_id={id}"
# r = requests.get(url)
# with open('test.xml','w',encoding='utf-8') as f:
#     f.write(r.text)

# twitch = Twitch()
# r = twitch.get_lives([''])
# print(r)

token = Jsondb.get_token('CWB_api')
time = '2023-01-03T05:46:45'
APIdata = requests.get(f'https://opendata.cwb.gov.tw/api/v1/rest/datastore/E-A0016-001?Authorization={token}&timeFrom={time}')
data = APIdata.json().get('records').get('Earthquake')[0]
print(EarthquakeReport(data))