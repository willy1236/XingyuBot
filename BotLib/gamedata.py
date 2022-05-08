import requests,datetime
from BotLib.basic import Database

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

class OsuPlayer():
    def __init__(self,data):
        self.username = data['username']
        self.id = data['id']
        self.global_rank = data['statistics']['global_rank']
        self.pp = data['statistics']['pp']
        self.avatar_url = data['avatar_url']
        self.country = data['country']["code"]
        self.is_online = data['is_online']

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
        self.pass_rate = round(data['passcount'] / data['playcount'],2)
        self.checksum = data['checksum']
        self.bpm = data['bpm']
        self.star = data['difficulty_rating']
        self.ar = data['ar']
        self.cs = data['cs']
        self.od = data['accuracy']
        self.hp = data['drain']
        self.version = data['version']

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

class ApexPlayer():
    def __init__(self,data):
        self.username = data['platformInfo']['platformUserId']
        self.platformSlug = data['platformInfo']['platformSlug']