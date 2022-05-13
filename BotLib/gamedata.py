import requests,datetime
from BotLib.basic import Database
from library import BRS

class OsuPlayer():
    def __init__(self,data):
        self.username = data['username']
        self.id = data['id']
        self.global_rank = data['statistics']['global_rank']
        self.pp = data['statistics']['pp']
        self.avatar_url = data['avatar_url']
        self.country = data['country']["code"]
        self.is_online = data['is_online']

        self.desplay = self.embed()

    def embed(self):
        embed = BRS.simple("Osu玩家資訊")
        embed.add_field(name="名稱",value=self.username)
        embed.add_field(name="id",value=self.id)
        embed.add_field(name="全球排名",value=self.global_rank)
        embed.add_field(name="pp",value=self.pp)
        embed.add_field(name="國家",value=self.country)
        embed.add_field(name="是否在線上",value=self.is_online)
        embed.set_thumbnail(url=self.avatar_url)
        return embed

class OsuBeatmap():
    def __init__(self,data):
        self.id = data['id']
        self.beatmapset_id = data['beatmapset_id']
        self.mode = data['mode']
        self.status = data['status']
        self.url = data['url']
        self.time = data['total_length']
        self.title = data['beatmapset']['title']
        self.cover = data['beatmapset']['covers']['cover']
        self.max_combo = data['max_combo']
        self.pass_rate = round(data['passcount'] / data['playcount'],3)
        self.checksum = data['checksum']
        self.bpm = data['bpm']
        self.star = data['difficulty_rating']
        self.ar = data['ar']
        self.cs = data['cs']
        self.od = data['accuracy']
        self.hp = data['drain']
        self.version = data['version']

        self.desplay = self.embed()

    def embed(self):
        embed = BRS.simple(title="Osu圖譜資訊")
        embed.add_field(name="名稱",value=self.title)
        embed.add_field(name="歌曲長度(秒)",value=self.time)
        embed.add_field(name="星數",value=self.star)
        embed.add_field(name="模式",value=self.mode)
        embed.add_field(name="combo數",value=self.max_combo)
        embed.add_field(name="圖譜狀態",value=self.status)
        embed.add_field(name="圖譜id",value=self.id)
        embed.add_field(name="圖譜組id",value=self.beatmapset_id)
        embed.add_field(name="通過率",value=self.pass_rate)
        embed.add_field(name="BPM",value=self.bpm)
        embed.add_field(name='網址', value='[點我]({0})'.format(self.url))
        embed.set_image(url=self.cover)
        return embed



class ApexPlayer():
    def __init__(self,data):
        self.username = data['platformInfo']['platformUserId']
        self.platformSlug = data['platformInfo']['platformSlug']

        self.desplay = self.embed()

    def embed(self):
        embed = BRS.simple("Apex玩家資訊")
        embed.add_field(name="名稱",value=self.username)
        embed.add_field(name="平台",value=self.platformSlug)
        return embed


class OsuData():
    def __init__(self):
        self.headers = self.get_osuheaders()
        self.API_URL = 'https://osu.ppy.sh/api/v2'

    @staticmethod
    def get_osuheaders():
        data = {
            'client_id': Database().osu_API_id,
            'client_secret': Database().osu_API_secret,
            'grant_type': 'client_credentials',
            'scope': 'public'
        }
        TOKEN_URL = 'https://osu.ppy.sh/oauth/token'
        response = requests.post(TOKEN_URL, data=data)
        token = response.json().get('access_token')
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {token}'
        }
        return headers

    def get_player(self,user):
        response = requests.get(f'{self.API_URL}/users/{user}', headers=self.headers).json()
        if 'error' not in response:
            return OsuPlayer(response)
        else:
            return None

    def get_beatmap(self,map):
        response = requests.get(f'{self.API_URL}/beatmaps/{map}', headers=self.headers).json()
        if 'error' not in response:
            return OsuBeatmap(response)
        else:
            return None

    def player_desplay(user:OsuPlayer):
            embed = BRS.simple("Osu玩家資訊")
            embed.add_field(name="名稱",value=user.username)
            embed.add_field(name="id",value=user.id)
            embed.add_field(name="全球排名",value=user.global_rank)
            embed.add_field(name="pp",value=user.pp)
            embed.add_field(name="國家",value=user.country)
            embed.add_field(name="是否在線上",value=user.is_online)
            embed.set_thumbnail(url=user.avatar_url)
            return embed


class ApexData():
    def __init__(self):
        self.headers = {
        'TRN-Api-Key': Database().TRN_API,
        'Accept': 'application/json',
        'Accept-Encoding': 'gzip'
        }
    
    def get_player(self,user):
        if user:
            response = requests.get(f'https://public-api.tracker.gg/v2/apex/standard/profile/origin/{user}', headers=self.headers)
            data = response.json().get('data')
            return ApexPlayer(data)
        else:
            return None
