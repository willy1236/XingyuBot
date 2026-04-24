import time
from datetime import date

import pandas as pd
from mwrogue.esports_client import EsportsClient

from starlib.database import APIType, sqldb

from ..base import APICaller
from .models import *


class RiotAPI(APICaller):
    url_tw2 = "https://tw2.api.riotgames.com"
    url_sea = "https://sea.api.riotgames.com"
    url_asia = "https://asia.api.riotgames.com"

    def __init__(self):
        self.key = sqldb.get_access_token(APIType.Riot).access_token
        self._headers = {"X-Riot-Token": self.key}
        super().__init__(headers=self._headers, base_url=self.url_asia)

        self._ddg_version = None

    @property
    def ddg_version(self):
        if not self._ddg_version:
            self._ddg_version = self.get_ddragon_version()
        return self._ddg_version

    def get_riot_account_byname(self, username: str):
        name, tag = username.split("#")
        r = self.get(f"riot/account/v1/accounts/by-riot-id/{name}/{tag}", base_url=self.url_asia)
        if r is None:
            return None
        return RiotUser(**r.json())

    def get_riot_account_bypuuid(self, puuid: str):
        r = self.get(f"riot/account/v1/accounts/by-puuid/{puuid}", base_url=self.url_asia)
        if r is None:
            return None
        return RiotUser(**r.json())

    def get_player_bypuuid(self, puuid: str):
        r = self.get(f"lol/summoner/v4/summoners/by-puuid/{puuid}", base_url=self.url_tw2)
        if r is None:
            return None
        return LOLPlayer(**r.json())

    def get_player_lol(self, riot_id: str):
        account = self.get_riot_account_byname(riot_id)
        if account:
            return self.get_player_bypuuid(account.puuid)

    def get_player_matchs(self, puuid: str, count=5, start=0, startTime: datetime | None = None) -> list[str]:
        params = {"start": 0, "count": count, "start": start}
        if startTime:
            params["startTime"] = int(startTime.timestamp())
        r = self.get(f"lol/match/v5/matches/by-puuid/{puuid}/ids", params=params, base_url=self.url_sea)
        return r.json()

    def get_match(self, matchId: str):
        r = self.get(f"lol/match/v5/matches/{matchId}", base_url=self.url_sea)
        return LOLMatch(**r.json())

    def get_summoner_masteries(self, puuid: str, count=5) -> list[LOLChampionMastery | None]:
        params = {"count": count}
        r = self.get(f"lol/champion-mastery/v4/champion-masteries/by-puuid/{puuid}/top", params=params, base_url=self.url_tw2)
        if r is None:
            return []
        return [LOLChampionMastery(**data) for data in r.json()]

    def get_summoner_active_match(self, puuid: str):
        r = self.get(f"lol/spectator/v5/active-games/by-summoner/{puuid}", base_url=self.url_tw2)
        if r is None:
            return None
        return LOLActiveMatch(r.json())

    def get_summoner_rank(self, puuid: str):
        r = self.get(f"lol/league/v4/entries/by-puuid/{puuid}", base_url=self.url_tw2)
        if r is None:
            return []
        return [LOLPlayerRank(**data) for data in r.json()]

    def get_rank_dataframe(self, riot_name: str, count=20):
        user = self.get_riot_account_byname(riot_name)
        if not user:
            return
        player = self.get_player_bypuuid(user.puuid)
        if not player:
            return
        match_ids = self.get_player_matchs(player.puuid, count=count)
        df = pd.DataFrame(columns=["name", "queueType", "tier", "rank"])
        participantId_list = []
        for id in match_ids:
            match = self.get_match(id)
            for participant in match.players:
                if participant.summonerid not in participantId_list:
                    participantId_list.append(participant.summonerid)
                    ranks = self.get_summoner_rank(participant.summonerid)
                    for rank in ranks:
                        new_row = {"name": rank.name, "queueType": rank.queueType, "tier": rank.tier, "rank": rank.rank}
                        df.loc[len(df)] = new_row
                        # pd.concat()
                time.sleep(1)
            time.sleep(1)
        return df

    def get_ddragon_version(self, all=False) -> str | list[str]:
        r = self.get("https://ddragon.leagueoflegends.com/api/versions.json")
        apidata = r.json()
        return apidata if all else apidata[0]


class OsuAPI(APICaller):
    base_url = "https://osu.ppy.sh/api/v2"

    def __init__(self):
        super().__init__()
        self.headers = self._get_headers()

    def _get_headers(self):
        ous_token = sqldb.get_identifier_secret(APIType.Osu)
        data = {"client_id": ous_token.client_id, "client_secret": ous_token.client_secret, "grant_type": "client_credentials", "scope": "public"}
        r = self._request("POST", "https://osu.ppy.sh/oauth/token", data=data)
        token = r.json().get("access_token")
        headers = {"Content-Type": "application/json", "Accept": "application/json", "Authorization": f"Bearer {token}"}
        return headers

    def get_player(self, userid: str):
        """獲取Osu玩家資訊"""
        response = self.get(f"users/{userid}").json()
        if "error" not in response:
            return OsuPlayer(response)
        else:
            return None

    def get_beatmap(self, beatmapid: str):
        """獲取Osu圖譜資訊"""
        response = self.get(f"beatmaps/{beatmapid}").json()
        if "error" not in response:
            return OsuBeatmap(response)
        else:
            return None

    def get_multiplayer(self, room, playlist):
        """獲取Osu多人遊戲資訊（未完成）"""
        r = self.get(f"rooms/{room}/playlist/{playlist}/scores")
        return OsuMultiplayer(r.json())

    def get_user_scores(self, user_id):
        """獲取Osu玩家分數"""
        r = self.get(f"users/{user_id}/scores/recent")
        return r.json()


class ApexAPI(APICaller):
    base_url = "https://api.mozambiquehe.re"

    def __init__(self, auth: str | None = None):
        self.auth = auth or sqldb.get_access_token(APIType.ApexStatue).access_token
        super().__init__()

    def get_player(self, username: str, platform: str = "PC"):
        params = {"auth": self.auth, "player": username, "platform": platform}
        r = self.get("bridge", params=params)
        return ApexPlayer(r.json())

    def get_map_rotation(self):
        params = {
            "auth": self.auth,
            "version": "2",
        }
        r = self.get("maprotation", params=params)
        return ApexMapRotation(**r.json())

    def get_raw_crafting(self) -> list | None:
        params = {"auth": self.auth}
        r = self.get("crafting", params=params)
        return r.json()

    def get_server_status(self):
        params = {"auth": self.auth}
        r = self.get("servers", params=params)
        return ApexStatus(r.json())


class SteamAPI(APICaller):
    base_url = "https://api.steampowered.com"

    def __init__(self):
        self.key = sqldb.get_access_token(APIType.Steam).access_token
        super().__init__()

    def get_user(self, userid):
        params = {"key": self.key, "steamids": userid}
        response = self.get("ISteamUser/GetPlayerSummaries/v0002/", params=params)
        if response.ok and response.json().get("response").get("players"):
            APIdata = response.json().get("response").get("players")[0]
            return SteamUser(**APIdata)
        else:
            return None

    def get_owned_games(self, userid):
        params = {"key": self.key, "steamid": userid, "include_appinfo": 1}
        response = self.get("IPlayerService/GetOwnedGames/v0001/", params=params)
        if response.ok:
            print(response.json())
            return SteamOwnedGame(**response.json().get("response"))
        else:
            return None


class DBDInterface(SteamAPI):
    def __init__(self):
        super().__init__()

    def get_player(self, steamid):
        user = SteamAPI().get_user(steamid)
        if user:
            params = {"steamid": user.steamid}
            response = self.get("api/playerstats", params=params, base_url="https://dbd.tricky.lol")
            if response.ok:
                return DBDPlayer(name=user.personaname, **response.json())
            else:
                return None
        else:
            return None


class LOLMediaWikiAPI:
    def __init__(self):
        self.site = EsportsClient("lol")

    def get_date_games(self, date: date):
        response = self.site.cargo_client.query(
            tables="ScoreboardGames=SG, Tournaments=T",
            join_on="SG.OverviewPage=T.OverviewPage",
            fields="T.Name=Tournament, T.TournamentLevel, SG.Gamename, SG.DateTime_UTC, SG.Team1, SG.Team2, SG.Winner, SG.Patch, SG.Gamelength, SG.Team1Players, SG.Team2Players, SG.Team1Kills, SG.Team2Kills, SG.Team1Picks, SG.Team2Picks",
            where="SG.DateTime_UTC >= '" + str(date) + " 00:00:00' AND SG.DateTime_UTC <= '" + str(date + timedelta(1)) + " 00:00:00'" + " AND T.TournamentLevel = 'Primary'",
            order_by="SG.DateTime_UTC",
        )

        return [dict(r) for r in response]


class MojangAPI(APICaller):
    base_url = "https://api.mojang.com"

    def get_uuid(self, username: str):
        r = self.get(f"users/profiles/minecraft/{username}")
        if r is None or r.status_code == 204:
            return None
        return MojangUser(**r.json())


class ZeroTierAPI(APICaller):
    base_url = "https://api.zerotier.com/api/v1"

    def __init__(self):
        self.auth = sqldb.get_access_token(APIType.ZeroTier).access_token
        super().__init__(headers={"Authorization": f"token {self.auth}", "Content-Type": "application/json"})

    def get_networks(self):
        r = self.get("network")
        return r.json()

    def get_network_members(self, network_id: str):
        r = self.get(f"network/{network_id}/member")
        return r.json()

    def get_unauthorized_members(self, network_id: str):
        members = self.get_network_members(network_id)
        return [member for member in members if not member["config"]["authorized"]]

    def get_member(self, network_id: str, member_id: str):
        r = self.get(f"network/{network_id}/member/{member_id}")
        if r is None:
            return None
        return r.json()

    def authorize_member(self, network_id: str, member_id: str, name: str | None = None, description: str | None = None):
        member = self.get_member(network_id, member_id)
        if not member:
            return None
        member["config"]["authorized"] = True
        if name:
            member["name"] = name
        if description:
            member["description"] = description
        r = self.post(f"network/{network_id}/member/{member_id}", data=member)
        return r.json()
