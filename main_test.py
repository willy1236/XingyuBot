import requests,genshin
import xml.etree.ElementTree as ET
import bothelper
from bothelper.interface.weather import EarthquakeReport
from bothelper.interface.game import RiotInterface
from bothelper import Jsondb,sqldb

# id ='UCgJR1i4QQ7O3yyrFROP_HvQ'
# url = f"https://www.youtube.com/feeds/videos.xml?channel_id={id}"
# r = requests.get(url)
# with open('test.xml','w',encoding='utf-8') as f:
#     f.write(r.text)