from BotLib.communitylib import Youtube
import requests

id ='UCgJR1i4QQ7O3yyrFROP_HvQ'
url = f"https://www.youtube.com/feeds/videos.xml?channel_id={id}"
r = requests.get(url)
print(r.text)
