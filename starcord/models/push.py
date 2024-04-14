from datetime import datetime,timezone,timedelta
from starcord.Utilities.utility import BotEmbed

class Youtube_Push:
    def __init__(self,data:dict):
        tz = timezone(timedelta(hours=8))
        self.id = data.get('id')
        self.video_id = data.get('videoId')
        self.channelid = data.get('channelId')
        self.title = data.get('title')
        self.link = data.get('link')
        self.author_name = data.get('author_name')
        self.author_url = data.get('author_uri')
        self.published = datetime.fromisoformat(data.get('published')).replace(tzinfo=tz)
        self.updated = datetime.strptime(data.get('updated')[:-10],'%Y-%m-%dT%H:%M:%S.%f').replace(tzinfo=tz) + timedelta(hours=8)
        
    def desplay(self):
        embed = BotEmbed.simple(title=self.title,
                                url=self.link,
                                description=f'[{self.author_name}]({self.author_url})')
        return embed


