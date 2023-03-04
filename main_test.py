import requests,genshin,asyncio
import xml.etree.ElementTree as ET
import bothelper
from bothelper.interface.weather import EarthquakeReport
from bothelper.interface.game import RiotInterface
from bothelper.interface.community import YoutubeInterface,Twitch
from bothelper.interface.user import RPGUser
#from bothelper import Jsondb,sqldb

# id ='UCgJR1i4QQ7O3yyrFROP_HvQ'
# url = f"https://www.youtube.com/feeds/videos.xml?channel_id={id}"
# r = requests.get(url)
# with open('test.xml','w',encoding='utf-8') as f:
#     f.write(r.text)

#interface = YoutubeInterface()
# channel_names = ['RSPHageeshow','汐SekiChannel']
# channel_ids = ['UCiEHmW7zRRZIjBsOKZ4s5AA','UCvuz0-GrFYmBe75bQa1yqtA']

# for i in channel_names:
#     r = interface.get_channel_id(i)

#interface.get_stream('UCwzpXmWAFEVKH3VzwvSlY_w')

# r =Twitch().get_user('rainteaorwhatever')
# print(r.login)
#interface.get_streams(channel_ids)
#user = RPGUser()
#print(user.id)