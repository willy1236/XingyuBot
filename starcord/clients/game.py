import requests
from starcord.database import Jsondb
from starcord.model.game import *
from starcord.errors import ClientError
class GameInterface():
    def __init__(self):
        self.db = Jsondb

class RiotClient(GameInterface):
    def __init__(self):
        super().__init__()
        self.url = 'https://tw2.api.riotgames.com'
        self.url_sea = 'https://sea.api.riotgames.com'
        self.key = Jsondb.get_token('riot')

    def get_player_byname(self,username):
        params = {
            'api_key':self.key
            }
        r = requests.get(f'{self.url}/lol/summoner/v4/summoners/by-name/{username}',params=params)
        if r.ok:
            return LOLPlayer(r.json())
        else:
            raise ClientError("lol_player",r.text)
        
    def get_player_bypuuid(self,puuid):
        params = {
            'api_key':self.key
            }
        r = requests.get(f'{self.url}/lol/summoner/v4/summoners/by-puuid/{puuid}',params=params)
        if r.ok:
            return LOLPlayer(r.json())
        else:
            raise ClientError("lol_player",r.text)

    def get_player_matchs(self,puuid,count=5) -> list[str]:
        params = {
            'api_key':self.key,
            'start':0,
            'count':count
            }
        r = requests.get(f'{self.url_sea}/lol/match/v5/matches/by-puuid/{puuid}/ids',params=params)
        if r.ok:
            return r.json()
        else:
            raise ClientError("lol_player_match",r.text)

    def get_match(self,matchId):
        params = {
            'api_key':self.key
            }
        r = requests.get(f'{self.url_sea}/lol/match/v5/matches/{matchId}',params=params)
        if r.ok:
            return LOLMatch(r.json())
        else:
            raise ClientError("lol_match",r.text)
    
class OsuInterface(GameInterface):
    def __init__(self):
        super().__init__()
        self._headers = self._get_headers()
        self._url = 'https://osu.ppy.sh/api/v2'

    def _get_headers(self):
        ous_token = self.db.get_token('osu')
        data = {
            'client_id': ous_token[0],
            'client_secret': ous_token[1],
            'grant_type': 'client_credentials',
            'scope': 'public'
        }
        r = requests.post('https://osu.ppy.sh/oauth/token', data=data)
        token = r.json().get('access_token')
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {token}'
        }
        return headers

    def get_player(self,userid:str):
        '''獲取Osu玩家資訊'''
        response = requests.get(f'{self._url}/users/{userid}', headers=self._headers).json()
        if 'error' not in response:
            return OsuPlayer(response)
        else:
            return None

    def get_beatmap(self,beatmapid:str):
        '''獲取Osu圖譜資訊'''
        response = requests.get(f'{self.__url}/beatmaps/{beatmapid}', headers=self._headers).json()
        if 'error' not in response:
            return OsuBeatmap(response)
        else:
            return None

    def get_multiplayer(self,room,playlist):
        '''獲取Osu多人遊戲資訊（未完成）'''
        r = requests.get(f'{self.__url}/rooms/{room}/playlist/{playlist}/scores',headers=self._headers)
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
        params={
            'auth':self.auth,
            'player':username,
            'platform':platform
        }
        r = requests.get(f'{self.url}/bridge',params=params)
        if r.status_code == 200:
            return ApexPlayer(r.json())
        else:
            return None
    
    def get_crafting(self):
        params={'auth':self.auth}
        r = requests.get(f'{self.url}/crafting',params=params)
        if r.status_code == 200:
            return ApexCrafting(r.json())
        else:
            return None
    
    def get_map_rotation(self):
        params={'auth':self.auth}
        r = requests.get(f'{self.url}/maprotation',params=params)
        if r.status_code == 200:
            return ApexMapRotation(r.json())
        else:
            return None  

    def get_server_status(self):
        params={'auth':self.auth}
        r = requests.get(f'{self.url}/servers',params=params)
        if r.status_code == 200:
            return ApexStatus(r.json())
        else:
            return None


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