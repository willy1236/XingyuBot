from BotLib.communitylib import Youtube
from BotLib.weatherlib import EarthquakeReport
from BotLib.database import Database
import requests
import xml.etree.ElementTree as ET


# id ='UCgJR1i4QQ7O3yyrFROP_HvQ'
# url = f"https://www.youtube.com/feeds/videos.xml?channel_id={id}"
# r = requests.get(url)
# with open('test.xml','w',encoding='utf-8') as f:
#     f.write(r.text)

data = requests.get(f'https://opendata.cwb.gov.tw/api/v1/rest/datastore/E-A0015-001?Authorization={Database().CWB_API}&limit=1')
with open('test.text','w',encoding='utf-8') as f:
    f.write(data.text)

