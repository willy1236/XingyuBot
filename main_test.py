from BotLib.interface.community import Twitch
from BotLib.database import Database
import requests
import xml.etree.ElementTree as ET
import bothelper


# id ='UCgJR1i4QQ7O3yyrFROP_HvQ'
# url = f"https://www.youtube.com/feeds/videos.xml?channel_id={id}"
# r = requests.get(url)
# with open('test.xml','w',encoding='utf-8') as f:
#     f.write(r.text)

# twitch = Twitch()
# r = twitch.get_lives([''])
# print(r)