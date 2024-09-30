import time

import requests
import pandas as pd

from starlib.fileDatabase import Jsondb
from starlib.models.game import *
from starlib.errors import APIInvokeError

class GameInterface():
    pass

class RiotAPI(GameInterface):
    def __init__(self):
        super().__init__()
        self.url_tw2 = 'https://tw2.api.riotgames.com'
        self.url_sea = 'https://sea.api.riotgames.com'
        self.url_asia = 'https://asia.api.riotgames.com'
        self.key = Jsondb.get_token("riot_api")
        self._headers = {
            'X-Riot-Token':self.key
        }

        self._ddg_version = None

    @property
    def ddg_version(self):
        if not self._ddg_version:
            self._ddg_version = self.get_ddragon_version()
        return self._ddg_version

    def get_riot_account_byname(self,username:str):
        name, tag = username.split('#')
        r = requests.get(f'{self.url_asia}/riot/account/v1/accounts/by-riot-id/{name}/{tag}', headers=self._headers)
        if r.ok:
            return RiotUser(r.json())
        elif r.status_code == 404:
            return None
        else:
            raise APIInvokeError("lol_player_byname",r.text)
        
    def get_player_bypuuid(self,puuid):
        r = requests.get(f'{self.url_tw2}/lol/summoner/v4/summoners/by-puuid/{puuid}',headers=self._headers)
        if r.ok:
            return LOLPlayer(r.json())
        elif r.status_code == 404:
            return None        
        else:
            raise APIInvokeError("lol_player_bypuuid",r.text)

    def get_player_matchs(self,puuid,count=5) -> list[str]:
        params = {
            'start':0,
            'count':count
            }
        r = requests.get(f'{self.url_sea}/lol/match/v5/matches/by-puuid/{puuid}/ids',params=params,headers=self._headers)
        if r.ok:
            return r.json()
        else:
            raise APIInvokeError("lol_player_match",r.text)

    def get_match(self,matchId):
        r = requests.get(f'{self.url_sea}/lol/match/v5/matches/{matchId}',headers=self._headers)
        if r.ok:
            return LOLMatch(**r.json())
        else:
            raise APIInvokeError("lol_match",r.text)
        
    def get_summoner_masteries(self, puuid, count=5) -> list[LOLChampionMastery | None]:
        params = {
            'count': count
            }
        r = requests.get(f'{self.url_tw2}/lol/champion-mastery/v4/champion-masteries/by-puuid/{puuid}/top',params=params,headers=self._headers)
        if r.ok:
            return [LOLChampionMastery(**data) for data in r.json()]
        elif r.status_code == 404:
            return []
        else:
            raise APIInvokeError("lol_summoner_masteries",r.text)
    
    def get_summoner_active_match(self,puuid):
        r = requests.get(f'{self.url_tw2}/lol/spectator/v5/active-games/by-summoner/{puuid}',headers=self._headers)
        if r.ok:
            return LOLActiveMatch(r.json())
        elif r.status_code == 404:
            return None
        else:
            raise APIInvokeError(f"lol_summoner_active_match:{r.text}")
        
    def get_summoner_rank(self,summoner_id):
        r = requests.get(f'{self.url_tw2}/lol/league/v4/entries/by-summoner/{summoner_id}',headers=self._headers)
        if r.ok:
            return [LOLPlayerRank(**data) for data in r.json()]
        elif r.status_code == 404:
            return []
        else:
            raise APIInvokeError(f"get_summoner_rank:{r.text}")

    def get_rank_dataframe(self,riot_name:str,count=20):
        user = self.get_riot_account_byname(riot_name)
        if not user:
            return
        player = self.get_player_bypuuid(user.puuid)
        if not player:
            return
        match_ids = self.get_player_matchs(player.puuid,count=count)
        df = pd.DataFrame(columns=['name', 'queueType', 'tier', 'rank'])
        participantId_list = []
        for id in match_ids:
            match = self.get_match(id)
            for participant in match.players:
                if participant.summonerid not in participantId_list:
                    participantId_list.append(participant.summonerid)
                    ranks = self.get_summoner_rank(participant.summonerid)
                    for rank in ranks:
                        new_row = {'name': rank.name, 'queueType': rank.queueType, 'tier': rank.tier, 'rank': rank.rank}
                        df.loc[len(df)] = new_row
                        #pd.concat()
                time.sleep(1)
            time.sleep(1)
        return df
    
    def get_ddragon_version(self,all=False) -> str | list[str]:
        r = requests.get('https://ddragon.leagueoflegends.com/api/versions.json')
        if r.ok:
            apidata = r.json()
            return apidata if all else apidata[0]
        else:
            raise APIInvokeError("ddragon_version",r.text)
    
class OsuAPI(GameInterface):
    def __init__(self):
        super().__init__()
        self._headers = self._get_headers()
        self._url = 'https://osu.ppy.sh/api/v2'

    def _get_headers(self):
        ous_token = Jsondb.get_token("osu_api")                   
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
        response = requests.get(f'{self._url}/beatmaps/{beatmapid}', headers=self._headers).json()
        if 'error' not in response:
            return OsuBeatmap(response)
        else:
            return None

    def get_multiplayer(self,room,playlist):
        '''獲取Osu多人遊戲資訊（未完成）'''
        r = requests.get(f'{self._url}/rooms/{room}/playlist/{playlist}/scores',headers=self._headers)
        if r.status_code == 200:
            return OsuMultiplayer(r.json())
        else:
            return None
        
    def get_user_scores(self,user_id):
        '''獲取Osu玩家分數'''
        r = requests.get(f'{self._url}/users/{user_id}/scores/recent',headers=self._headers)
        if r.status_code == 200:
            return r.json()
        else:
            return None


class ApexInterface(GameInterface):
    def __init__(self):
        super().__init__()
        self.auth = Jsondb.get_token("apex_status_API")
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
    
    def get_raw_crafting(self) -> list | None:
        params={'auth':self.auth}
        r = requests.get(f'{self.url}/crafting',params=params)
        if r.ok:
            return r.json()
        else:
            return None
        
    def get_crafting_from_chche(self):
        apex_crafting = Jsondb.cache.get("apex_crafting")
        if apex_crafting:
            return ApexCrafting(apex_crafting['data'])

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
        self.key = Jsondb.get_token("steam_api")

    def get_user(self,userid):
        params = {
            'key':self.key,
            'steamids':userid
        }
        response = requests.get('https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/',params=params)
        if response.ok and response.json().get('response').get('players'):
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
            if response.ok:
                return DBDPlayer(response.json(),user.name)
            else:
                return None
        else:
            return None