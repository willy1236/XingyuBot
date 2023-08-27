import requests
from starcord.database import Jsondb,sqldb
from starcord.model.game import *
from starcord.errors import ClientError
class GameInterface():
    def __init__(self):
        self.db = Jsondb

class RiotClient(GameInterface):
    def __init__(self):
        super().__init__()
        self.url_tw2 = 'https://tw2.api.riotgames.com'
        self.url_sea = 'https://sea.api.riotgames.com'
        self.key = Jsondb.get_token('riot')
        self.headers = {
            'X-Riot-Token':self.key
        }

    def get_player_data(self,summoner_name=None,discord_id=None):
        """
        從資料庫取得資料，若沒有則從API取得
        :param summoner_name: 召喚師名稱
        :param discord_id: 若提供則先查詢資料庫
        """
        if discord_id:
            dbdata = sqldb.get_game_data(discord_id,"lol")
            if dbdata:
                return PartialLOLPlayer(dbdata)
        
        if summoner_name:
            return self.get_player_byname(summoner_name)


    def get_player_byname(self,username):
        r = requests.get(f'{self.url_tw2}/lol/summoner/v4/summoners/by-name/{username}',headers=self.headers)
        if r.ok:
            return LOLPlayer(r.json())
        elif r.status_code == 404:
            return None
        else:
            raise ClientError("lol_player_byname",r.text)
        
    def get_player_bypuuid(self,puuid):
        r = requests.get(f'{self.url_tw2}/lol/summoner/v4/summoners/by-puuid/{puuid}',headers=self.headers)
        if r.ok:
            return LOLPlayer(r.json())
        elif r.status_code == 404:
            return None        
        else:
            raise ClientError("lol_player_bypuuid",r.text)

    def get_player_matchs(self,puuid,count=5) -> list[str]:
        params = {
            'start':0,
            'count':count
            }
        r = requests.get(f'{self.url_sea}/lol/match/v5/matches/by-puuid/{puuid}/ids',params=params,headers=self.headers)
        if r.ok:
            return r.json()
        else:
            raise ClientError("lol_player_match",r.text)

    def get_match(self,matchId):
        r = requests.get(f'{self.url_sea}/lol/match/v5/matches/{matchId}',headers=self.headers)
        if r.ok:
            return LOLMatch(r.json())
        else:
            raise ClientError("lol_match",r.text)
        
    def get_summoner_masteries(self,summoner_id) -> list[LOLChampionMasteries | None]:
        params = {
            'count':5
            }
        r = requests.get(f'{self.url_tw2}/lol/champion-mastery/v4/champion-masteries/by-summoner/{summoner_id}/top',params=params,headers=self.headers)
        if r.ok:
            return [LOLChampionMasteries(data) for data in r.json()]
        elif r.status_code == 404:
            return []
        else:
            raise ClientError("lol_summoner_masteries",r.text)
    
    def get_summoner_active_match(self,summoner_id):
        r = requests.get(f'{self.url_tw2}/lol/spectator/v4/active-games/by-summoner/{summoner_id}',headers=self.headers)
        if r.ok:
            return LOLActiveMatch(r.json())
        elif r.status_code == 404:
            return None
        else:
            raise ClientError(f"lol_summoner_active_match:{r.text}")
        
    def get_summoner_rank(self,summoner_id):
        r = requests.get(f'{self.url_tw2}/lol/league/v4/entries/by-summoner/{summoner_id}',headers=self.headers)
        if r.ok:
            return [LOLPlayerRank(data) for data in r.json()]
        elif r.status_code == 404:
            return []
        else:
            raise ClientError(f"get_summoner_rank:{r.text}")
    
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
        if r.ok:
            return ApexPlayer(r.json())
        else:
            return None
    
    def get_crafting(self):
        params={'auth':self.auth}
        r = requests.get(f'{self.url}/crafting',params=params)
        if r.ok:
            return ApexCrafting(r.json())
        else:
            return None
    
    def get_map_rotation(self):
        params={'auth':self.auth}
        r = requests.get(f'{self.url}/maprotation',params=params)
        if r.ok:
            apidata = r.json()
            if apidata:
                return ApexMapRotation(apidata)
        else:
            return None
    
    def get_raw_map_rotation(self) -> dict | None:
        params={'auth':self.auth}
        r = requests.get(f'{self.url}/maprotation',params=params)
        if r.ok:
            return r.json()
        else:
            return None
        
    def get_map_rotation_from_chche(self):
        apex_map = Jsondb.read_cache("apex_map")
        if apex_map:
            return ApexMapRotation(apex_map['data'])

    def get_server_status(self):
        params={'auth':self.auth}
        r = requests.get(f'{self.url}/servers',params=params)
        if r.ok:
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


# class hoyoInterface(GameInterface):
#     def __init__(self,dcid):
#         super().__init__()
#         cookies = {}
#         self.__client = genshin.Client(cookies) 