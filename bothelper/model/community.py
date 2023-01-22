import datetime,discord

class TwitchUser():
    pass

class TwitchStream():
    def __init__(self,data):
        self.id = data.get('id')
        self.user = data.get('user_login')
        self.username = data.get('user_name')
        
        self.game_id = data.get('game_id')
        self.game_name = data.get('game_name')
        
        self.title = data.get('title')
        self.viewer_count = data.get('viewer_count')
        self.thumbnail_url = data.get('thumbnail_url').replace('{width}','960').replace('{height}','540')
        self.starttime = (datetime.datetime.strptime(data.get('started_at'),'%Y-%m-%dT%H:%M:%SZ')+datetime.timedelta(hours=8)).strftime('%Y/%m/%d %H:%M:%S')
        self.tags = data.get('tags')
        self.url = f"https://www.twitch.tv/{self.user}"
        
        self.display = self.embed()

    def embed(self):
        embed = discord.Embed(
            title=self.title,
            url=self.url,
            description=self.game_name,
            color=0x6441a5,
            timestamp = datetime.datetime.now()
            )
        embed.set_author(name=f"{self.username} 開台啦！")
        embed.set_image(url=self.thumbnail_url)
        embed.set_footer(text=f"開始於{self.starttime}")
        return embed