import datetime
from bothelper.utility import BotEmbed

class Youtube_Push:
    def __init__(self,data:dict):
        tz = datetime.timezone(datetime.timedelta(hours=8))
        {'id': 'yt:video:L3pnOeAea80', 'videoId': 'L3pnOeAea80', 'channelId': 'UCbh7KHPMgYGgpISdbF6l0Kw', 'title': '【輕聲細語】全肯定。溫柔。哄睡。🌼 #瑪格麗特諾爾絲 #箱箱TheBox', 'link': 'https://www.youtube.com/watch?v=L3pnOeAea80', 'author_name': '瑪格麗特 · 諾爾絲 / Margaret North【箱箱The Box所屬】', 'author_uri': 'https://www.youtube.com/channel/UCbh7KHPMgYGgpISdbF6l0Kw', 'published': '2023-04-07T17:15:34+00:00', 'updated': '2023-04-07T17:15:56.88236001+00:00'}
        self.id = data.get('id')
        self.video_id = data.get('videoId')
        self.channelid = data.get('channelId')
        self.title = data.get('title')
        self.link = data.get('link')
        self.author_name = data.get('author_name')
        self.author_url = data.get('author_uri')
        self.published = datetime.datetime.fromisoformat(data.get('published')).replace(tzinfo=tz)
        self.updated = datetime.datetime.fromisoformat(data.get('updated')).replace(tzinfo=tz)
        
    def desplay(self):
        embed = BotEmbed.simple(title=self.title,
                                url=self.url,
                                description=f'[{self.author_name}]({self.author_url})')
        return embed


