import requests,genshin
from bothelper.database import Jsondb
from bothelper.model.game import *

class GameInterface():
    def __init__(self):
        self.db = Jsondb

class RiotInterface(GameInterface):
    def __init__(self):
        super().__init__()
        self.url = 'https://tw2.api.riotgames.com'
        self.url_sea = 'https://sea.api.riotgames.com'
        self.key = self.db.get_token('riot')

    def get_lolplayer(self,userid):
        params = {
            'api_key':self.key
            }
        r = requests.get(f'{self.url}/lol/summoner/v4/summoners/by-name/{userid}',params=params)
        if r.status_code == 200:
            return LOLPlayer(r.json())
        else:
            print('lol_player:',r.text)
            return None

    def get_lol_player_match(self,puuid,count=5) -> list[str]:
        params = {
            'api_key':self.key,
            'start':0,
            'count':count
            }
        r = requests.get(f'{self.url_sea}/lol/match/v5/matches/by-puuid/{puuid}/ids',params=params)
        if r.status_code == 200:
            return r.json()
        else:
            print('lol_player_match:',r.text)
            return None

    def get_lol_match(self,matchId):
        params = {
            'api_key':self.key
            }
        r = requests.get(f'{self.url_sea}/lol/match/v5/matches/{matchId}',params=params)
        if r.status_code == 200:
            return LOLMatch(r.json())
        else:
            print('lol_match:',r.text)
            return None
    
class OsuInterface(GameInterface):
    def __init__(self):
        super().__init__()
        self.__headers = self.get_headers()
        self.__url = 'https://osu.ppy.sh/api/v2'

    def get_headers(self):
        ous_token = self.db.get_token('osu')
        data = {
            'client_id': ous_token[0],
            'client_secret': ous_token[1],
            'grant_type': 'client_credentials',
            'scope': 'public'
        }
        response = requests.post('https://osu.ppy.sh/oauth/token', data=data)
        token = response.json().get('access_token')
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {token}'
        }
        return headers

    def get_player(self,userid:str):
        '''獲取Osu玩家資訊'''
        response = requests.get(f'{self.__url}/users/{userid}', headers=self.__headers).json()
        if 'error' not in response:
            return OsuPlayer(response)
        else:
            return None

    def get_beatmap(self,beatmapid:str):
        '''獲取Osu圖譜資訊'''
        response = requests.get(f'{self.__url}/beatmaps/{beatmapid}', headers=self.__headers).json()
        if 'error' not in response:
            return OsuBeatmap(response)
        else:
            return None

    def get_multiplayer(self,room,playlist):
        '''獲取Osu多人遊戲資訊（未完成）'''
        r = requests.get(f'{self.__url}/rooms/{room}/playlist/{playlist}/scores',headers=self.__headers)
        if r.status_code == 200:
            return OsuMultiplayer(r.json())
        else:
            return None


class ApexInterface(GameInterface):
    def __init__(self):
        super().__init__()
        self.auth = self.db.get_token('apex')
        self.url = 'https://api.mozambiquehe.re'

    def get_player(self,username:str,platform:str='PC'):
        try:
            params={
                'auth':self.auth,
                'player':username,
                'platform':platform
            }
            response = requests.get(f'{self.url}/bridge',params=params).json()
            return ApexPlayer(response)
        except:
            return None
    
    def get_crafting(self):
        params={'auth':self.auth}
        response = requests.get(f'{self.url}/crafting',params=params).json()
        if "Error" in response or not response:
            return None
        else:
            return ApexCrafting(response)
    
    def get_map_rotation(self):
        params={'auth':self.auth}
        response = requests.get(f'{self.url}/maprotation',params=params).json()
        if "Error" in response or not response:
            return None
        else:    
            return ApexMapRotation(response)

    def get_server_status(self):
        params={'auth':self.auth}
        response = requests.get(f'{self.url}/servers',params=params).json()
        return ApexStatus(response)


class SteamInterface(GameInterface):
    def __init__(self):
        super().__init__()
        self.key = self.db.get_token('steam')

    def get_user(self,userid):
        params = {
            'key':self.key,
            'steamids':userid
        }
        response = requests.get('https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/',params=params)
        if response.status_code == 200 and response.json().get('response').get('players'):
            APIdata = response.json().get('response').get('players')[0]
            return SteamUser(APIdata)
        else:
            return None


class DBDInterface(SteamInterface):
    def __init__(self):
        super().__init__()

    def get_player(self,steamid):
        user = SteamInterface().get_user(steamid)
        if user:
            params = {'steamid':user.id}
            response = requests.get('https://dbd.tricky.lol/api/playerstats', params=params)
            if response.status_code == 200:
                return DBDPlayer(response.json(),user.name)
            else:
                return None
        else:
            return None


class hoyoInterface(GameInterface):
    def __init__(self,dcid):
        super().__init__()
        cookies = {}
        self.__client = genshin.Client(cookies) 