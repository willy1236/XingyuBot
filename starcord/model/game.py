from datetime import datetime,timedelta
from starcord.utility import BotEmbed
from starcord.database import Jsondb,csvdb

jdict = Jsondb.jdict
lol_jdict = Jsondb.lol_jdict

class LOLPlayer():
    def __init__(self,data):
        self.name = data.get('name')
        self.summonerid = data.get('id')
        self.accountid = data.get('accountId')
        self.puuid = data.get('puuid')
        self.summonerLevel = data.get('summonerLevel')
        self.profileIconId = data.get('profileIconId')

    def desplay(self):
        embed = BotEmbed.general(self.name)
        #embed.add_field(name="玩家名稱", value=self.name, inline=False)
        embed.add_field(name="召喚師等級", value=self.summonerLevel, inline=False)
        embed.add_field(name="帳號ID", value=self.accountid, inline=False)
        embed.add_field(name="召喚師ID", value=self.summonerid, inline=False)
        embed.add_field(name="puuid", value=self.puuid, inline=False)
        try:
            embed.set_thumbnail(url=f'https://ddragon.leagueoflegends.com/cdn/13.15.1/img/profileicon/{self.profileIconId}.png')
        except:
            embed.set_thumbnail(url='https://i.imgur.com/B0TMreW.png')
        embed.set_footer(text="puuid是全球唯一的ID，不隨帳號移動地區而改變")
        
        return embed

class PartialLOLPlayer(LOLPlayer):
    def __init__(self,data):
        super().__init__(data)
        self.discord_id = data.get('user_id')
        self.name = data.get('player_name')
        self.summonerid = data.get('player_id')
        self.accountid = data.get('account_id')
        self.puuid = data.get('other_id')

class LOLPlayerInMatch():
    def __init__(self,data):
        #self.participantId = data['participantId']
        #self.profileIcon = data['profileIcon']
        #self.puuid = data['puuid']
        self.summonerId = data['summonerId']
        self.summonerLevel = data['summonerLevel']
        self.summonerName = data['summonerName']

        self.assists = data['assists']
        self.deaths = data['deaths']
        self.kills = data['kills']
        self.lane = data['lane']
        self.visionScore = data['visionScore']
        self.role = data['role']
        self.kda = round((self.kills + self.assists) / self.deaths, 2) if self.deaths > 0 else (self.kills + self.assists)
        self.win = data['win']

        self.doubleKills = data['doubleKills']
        self.tripleKills = data['tripleKills']
        self.quadraKills = data['quadraKills']
        self.pentaKills = data['pentaKills']
        self.largestMultiKill = data['largestMultiKill']
        self.soloKills = data['challenges']['soloKills']
        
        self.dragonKills = data['dragonKills']
        self.baronKills = data['baronKills']

        self.championId = data['championId']
        self.championName = data['championName']
        self.champLevel = data['champLevel']
        
        self.totalDamageDealt = data['totalDamageDealt']
        self.totalDamageDealtToChampions = data['totalDamageDealtToChampions']
        self.totalDamageTaken = data['totalDamageTaken']
        self.totalHeal = data['totalHeal']
        self.totalTimeCCDealt = data['totalTimeCCDealt']

        self.enemyMissingPings = data['enemyMissingPings']

        self.firstBloodKill = data['firstBloodKill']
        #self.firstBloodAssist = data['firstBloodAssist']
        self.firstTowerKill = data['firstTowerKill']
        #self.firstTowerAssist = data['firstTowerAssist']

        self.gameEndedInEarlySurrender = data['gameEndedInEarlySurrender']
        self.gameEndedInSurrender = data['gameEndedInSurrender']
        #self.teamEarlySurrendered = data['teamEarlySurrendered']
        self.goldEarned = data['goldEarned']
        self.goldSpent = data['goldSpent']
        self.totalMinionsKilled = data['totalMinionsKilled']
        self.laneMinionsFirst10Minutes = data['challenges']['laneMinionsFirst10Minutes']
        self.jungleCsBefore10Minutes = round(data['challenges']['jungleCsBefore10Minutes'])
        self.AllMinionsBefore10Minutes =self.laneMinionsFirst10Minutes + self.jungleCsBefore10Minutes * 10
        self.bountyGold = data['challenges']['bountyGold']

        self.damagePerMinute = data['challenges']['damagePerMinute']
        self.damageTakenOnTeamPercentage = round(data['challenges']['damageTakenOnTeamPercentage'] * 100, 1)
        self.goldPerMinute = round(data['challenges']['goldPerMinute'])

        self.teamDamagePercentage = round(data['challenges']['teamDamagePercentage'] * 100, 1)
        self.visionScorePerMinute = round(data['challenges']['visionScorePerMinute'], 2)
        #self.items = [ data['item0'],data['item1'],data['item2'],data['item3'],data['item4'],data['item5'],data['item6'] ]

    def desplaytext(self):
        text = f'`{self.summonerName}(LV. {self.summonerLevel})`\n'
        name_csv = csvdb.get_row_by_column_value(csvdb.lol_champion,"name_en",self.championName)
        name = name_csv.loc["name_tw"] if not name_csv.empty else self.championName
        text += f'{name}(LV. {self.champLevel})\n'
        lane = lol_jdict['road'].get(self.lane) or self.lane
        if self.role != "NONE":
            lane +=f" {self.role}"
        text += f'{lane}\n'
        text += f'{self.kills}/{self.deaths}/{self.assists} KDA: {self.kda} solokill：{self.soloKills}\n'
        text += f'視野分：{self.visionScore} ({self.visionScorePerMinute}/min)\n'
        text += f'連殺：{self.doubleKills}/{self.tripleKills}/{self.quadraKills}/{self.pentaKills}\n'
        text += f'輸出：{self.totalDamageDealtToChampions} ({self.teamDamagePercentage}%)\n'
        text += f'承受：{self.totalDamageTaken} ({self.damageTakenOnTeamPercentage}%)\n'
        #text += f'治療/CC：{self.totalHeal}/{self.totalTimeCCDealt}\n'
        text += f'經濟：{self.goldEarned} ({self.goldPerMinute}/min)\n'
        text += f'吃兵/前10分鐘：{self.totalMinionsKilled}/{self.AllMinionsBefore10Minutes}\n'
        text += f'小龍/巴龍：{self.dragonKills}/{self.baronKills}\n'
        text += f'個人賞金：{self.bountyGold}\n'
        text += f'Ping問號燈：{self.enemyMissingPings}\n'

        if self.firstBloodKill and self.firstTowerKill:
            text += f'首殺+首塔🔪 '
        elif self.firstBloodKill:
            text += f'首殺🔪 '
        elif self.firstTowerKill:
            text += f'首塔🔪 '

        if self.gameEndedInEarlySurrender:
            text += f'提早投降🏳️'
        elif self.gameEndedInSurrender:
            text += f'投降🏳️'
        text += '\n'
        
        return text

class LOLTeamInMatch():
    def __init__(self,data):
        #100 = blue, 200 = red
        self.teamId = data['teamId']
        self.win = data['win']
        self.bans = data['bans']
        
        self.baronKill = data['objectives']['baron']['kills']
        self.dragonKill = data['objectives']['dragon']['kills']
        #riftHerald = 預示者
        self.riftHeraldKill = data['objectives']['riftHerald']['kills']
        
        self.championKill = data['objectives']['champion']['kills']
        #inhibitor = 水晶兵營
        self.inhibitorKill = data['objectives']['inhibitor']['kills']
        self.towerKill = data['objectives']['tower']['kills']


class LOLMatch():
    def __init__(self,data):
        self.matchId = data['metadata']['matchId']

        self.gameStartTimestamp = data['info']['gameStartTimestamp']
        self.gameDuration = data['info']['gameDuration']
        self.gameEndTimestamp = data['info']['gameEndTimestamp']

        self.gameId = data['info']['gameId']
        self.gameMode = data['info']['gameMode']
        self.gameVersion = data['info']['gameVersion']
        self.mapId = data['info']['mapId']
        self.platformId = data['info']['platformId']
        self.tournamentCode = data['info']['tournamentCode']

        self.participants = data['info']['participants']
        self.teams = data['info']['teams']

        self.players = [LOLPlayerInMatch(i) for i in self.participants]
        self.team = [LOLTeamInMatch(i) for i in self.teams]
    
    def desplay(self):
        embed = BotEmbed.simple("LOL對戰")
        gamemode = lol_jdict['mod'].get(self.gameMode) or self.gameMode
        embed.add_field(name="遊戲模式", value=gamemode, inline=False)
        embed.add_field(name="對戰ID", value=self.matchId, inline=False)
        embed.add_field(name="遊戲版本", value=self.gameVersion, inline=False)
        minutes = str(self.gameDuration // 60)
        seconds = str(self.gameDuration % 60)
        time = f"{minutes}:{seconds}"
        embed.add_field(name="遊戲時長", value=time, inline=False)
        blue = ''
        red = ''
        i = 0
        for player in self.players:
            if i < 5:
                blue += player.desplaytext()
                if i != 4:
                    blue += '\n'
            else:
                red += player.desplaytext()
                if i != 9:
                    red += '\n'
            i+=1
        if self.team[0].win:
            embed.add_field(name="藍方👑", value=blue, inline=True)
            embed.add_field(name="紅方", value=red, inline=True)
        else:
            embed.add_field(name="藍方", value=blue, inline=True)
            embed.add_field(name="紅方👑", value=red, inline=True)
        return embed
    
    def get_player_in_match(self,playername):
        for player in self.players:
            if player.summonerName == playername:
                return player
    
class LOLChampionMasteries(LOLPlayer):
    def __init__(self,data):
        #unused:puuid, summonerId
        super().__init__(data)
        self.championId = data['championId']
        self.championLevel = data['championLevel']
        self.championPoints = data['championPoints']
        self.lastPlayTime = data['lastPlayTime']
        self.championPointsSinceLastLevel = data['championPointsSinceLastLevel']
        self.championPointsUntilNextLevel = data['championPointsUntilNextLevel']
        self.chestGranted = data['chestGranted']
        self.tokensEarned = data['tokensEarned']

class LOLPlayerRank(LOLPlayer):
    def __init__(self,data):
        super().__init__(data)
        self.leagueId = data.get("leagueId")
        self.queueType = data.get("queueType")
        self.tier = data.get("tier")
        self.rank = data.get("rank")
        self.leaguePoints = data.get("leaguePoints")
        self.wins = data.get("wins")
        self.losses = data.get("losses")
        self.veteran = data.get("veteran")
        self.inactive = data.get("inactive")
        self.freshBlood = data.get("freshBlood")
        self.hotStreak = data.get("hotStreak")

    def desplay(self):
        embed = BotEmbed.simple(self.queueType)
        embed.add_field(name="牌位", value=f"{self.tier} {self.rank}", inline=False)
        embed.add_field(name="聯盟分數", value=self.leaguePoints, inline=False)
        embed.add_field(name="勝敗", value=f"{self.wins}/{self.losses} {(round(self.wins / (self.wins + self.losses),3)) * 100}%", inline=False)

        return embed

class LOLActiveMatch:
    def __init__(self,data):
        self.gameId = data.get("gameId")
        self.mapId = data.get("mapId")
        self.gameMode = data.get("gameMode")
        self.gameType = data.get("gameType")
        self.platformId = data.get("platformId")
        self.gameStartTime = data.get("gameStartTime")
        self.gameLength = data.get("gameLength")
        self.participants = [LOLLActiveMatchPlayer(i) for i in data.get("participants")]
        self.bannedChampions = [LOLBanChampion(i) for i in data.get("bannedChampions")]
    
    def desplay(self):
        embed = BotEmbed.simple("LOL對戰")
        gamemode = lol_jdict['mod'].get(self.gameMode) or self.gameMode
        embed.add_field(name="遊戲模式", value=gamemode, inline=False)
        embed.add_field(name="開始時間", value=f"<t:{str(self.gameStartTime)[:-3]}>", inline=False)
        if self.gameLength <= 0:
            time = "尚未開始"
        else:
            minutes = str(self.gameLength // 60)
            seconds = str(self.gameLength % 60)
            time = f"{minutes}:{seconds}"
        embed.add_field(name="遊戲時長", value=time, inline=False)
        
        if self.bannedChampions:
            ban_champions = [ban_champion.name for ban_champion in self.bannedChampions]
            embed.add_field(name="禁用角色", value=" ".join(ban_champions), inline=False)
        blue = ''
        red = ''
        i = 0
        for player in self.participants:
            if i < 5:
                blue += player.desplaytext()
                if i != 4:
                    blue += '\n'
            else:
                red += player.desplaytext()
                if i != 9:
                    red += '\n'
            i+=1
        embed.add_field(name="藍方", value=blue, inline=True)
        embed.add_field(name="紅方", value=red, inline=True)
        return embed

class LOLLActiveMatchPlayer:
    def __init__(self,data):
        self.teamId = data.get("teamId")
        self.spell1Id = data.get("spell1Id")
        self.spell2Id = data.get("spell2Id")
        self.championId = data.get("championId")
        self.profileIconId = data.get("profileIconId")
        self.summonerName = data.get("summonerName")
        self.bot = data.get("bot")
        self.summonerId = data.get("summonerId")
        
        self.perks = data.get("perks")
        self.mainperk = self.perks.get("perkIds")[0]
        self.perkStyle = self.perks.get("perkStyle")
        self.perkSubStyle = self.perks.get("perkSubStyle")

    def desplaytext(self):
        text = f'`{self.summonerName}`\n'
        name_csv = csvdb.get_row_by_column_value(csvdb.lol_champion,"champion_id",self.championId)
        name = name_csv.loc["name_tw"] if not name_csv.empty else self.championId
        if not self.bot:
            text += f'{name}\n'
        else:
            text += f'{name}（機器人）\n'

        text += f'召喚師技能：{lol_jdict["summoner_spell"].get(str(self.spell1Id))}/{lol_jdict["summoner_spell"].get(str(self.spell2Id))}\n'
        text += f'主符文：{lol_jdict["runes"].get(str(self.perkStyle))}/{lol_jdict["runes"].get(str(self.mainperk))}\n'
        text += f'副符文：{lol_jdict["runes"].get(str(self.perkSubStyle))}\n'
        
        return text

class LOLBanChampion:
    __slots__= [
        "championId",
        "teamId",
        "pickTurn",
        "name",
    ]

    def __init__(self,data):
        self.championId = data.get("championId")
        self.teamId = data.get("teamId")
        self.pickTurn = data.get("pickTurn")
        name_csv = csvdb.get_row_by_column_value(csvdb.lol_champion,"champion_id",self.championId)
        name = name_csv.loc["name_tw"] if not name_csv.empty else str(self.championId)
        self.name = name

class OsuPlayer():
    def __init__(self,data):
        self.name = data['username']
        self.id = data['id']
        self.global_rank = data['statistics']['global_rank']
        self.country_rank = data['statistics']['country_rank']
        self.pp = data['statistics']['pp']
        self.avatar_url = data['avatar_url']
        self.country = data['country']["code"]
        self.is_online = data['is_online']
        self.level = data['statistics']['level']['current']
        self.max_level = data['statistics']['level']['progress']
        self.max_combo = data['statistics']['maximum_combo']
        #self.last_visit = datetime.datetime.strptime(data['last_visit'],"%Y-%m-%dT%H:%M:%S%Z")
        self.oragin_last_visit = datetime.strptime(data['last_visit'],"%Y-%m-%dT%H:%M:%S%z")
        self.e8_last_visit = self.oragin_last_visit + timedelta(hours = 8)
        self.last_visit = self.e8_last_visit.strftime('%Y-%m-%d %H:%M:%S')
        self.url = f'https://osu.ppy.sh/users/{self.id}'

    def desplay(self):
        embed = BotEmbed.general("Osu玩家資訊",url=self.url)
        embed.add_field(name="名稱",value=self.name)
        embed.add_field(name="id",value=self.id)
        embed.add_field(name="全球排名",value=self.global_rank)
        embed.add_field(name="地區排名",value=self.country_rank)
        embed.add_field(name="pp",value=self.pp)
        embed.add_field(name="國家",value=self.country)
        embed.add_field(name="等級",value=f'{self.level}({self.max_level}%)')
        embed.add_field(name="最多連擊數",value=self.max_combo)
        if self.is_online:
            embed.add_field(name="最後線上",value='Online')
        else:
            embed.add_field(name="最後線上",value=self.last_visit)
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

    def desplay(self):
        embed = BotEmbed.simple(title="Osu圖譜資訊")
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

class OsuMultiplayer:
    def __init__(self,data):
        print(data)


class ApexPlayer():
    def __init__(self,data):
        #basic information
        self.name = data['global']['name']
        self.id = data['global']['uid']
        self.platform = data['global']['platform']
        self.level = data['global']['level']
        self.avatar = data['global']['avatar']
        #bans
        self.bans = data['global']['bans']
        #rank
        self.rank = data['global']['rank']['rankName']
        if data['global']['rank']['rankName'] != "Unranked":
            self.rank += " "+str(data['global']['rank']['rankDiv'])
        self.rank_score = data['global']['rank']['rankScore']
        self.arena_rank = data['global']['arena']['rankName']
        if data['global']['arena']['rankName'] != "Unranked":
            self.arena_rank += " "+str(data['global']['arena']['rankDiv'])
        self.arena_score = data['global']['arena']['rankScore']
        #state
        self.now_state =  data['realtime']['currentStateAsText']
        #selected
        self.legends_selected_name = data['legends']['selected']['LegendName']
        self.legends_selected_tacker = data['legends']['selected']['data']
        self.legends_selected_banner = data['legends']['selected']['ImgAssets']['banner'].replace(" ","%20")

    def desplay(self):
        embed = BotEmbed.simple("Apex玩家資訊")
        embed.add_field(name="名稱",value=self.name)
        embed.add_field(name="id",value=self.id)
        embed.add_field(name="平台",value=self.platform)
        embed.add_field(name="等級",value=self.level)
        embed.add_field(name="牌位階級",value=self.rank)
        embed.add_field(name="牌位分數",value=self.rank_score)
        embed.add_field(name="競技場牌位階級",value=self.arena_rank)
        embed.add_field(name="競技場牌位分數",value=self.arena_score)
        embed.add_field(name="目前狀態",value=self.now_state)
        if self.bans['isActive']:
            embed.add_field(name="目前ban狀態",value=self.bans['remainingSeconds'])
        else:
            embed.add_field(name="目前ban狀態",value=self.bans['isActive'])
        embed.add_field(name="目前選擇角色",value=self.legends_selected_name)
        embed.set_image(url=self.legends_selected_banner)
        return embed

class ApexCrafting():
    def __init__(self,data):
        self.daily = data[0]
        self.weekly = data[1]

        self.daily_start = self.daily['startDate']
        self.daily_end = self.daily['endDate']
        self.daily_item = [ApexCraftingItem(i) for i in self.daily['bundleContent']]

        self.weekly_start = self.weekly['startDate']
        self.weekly_end = self.weekly['endDate']
        self.weekly_item = [ApexCraftingItem(i) for i in self.weekly['bundleContent']]
    
    def desplay(self):
        embed = BotEmbed.simple("Apex合成器內容")
        text = ""
        for item in self.daily_item:
            text += f"{item.name_tw} {item.cost}\n"
        embed.add_field(name="每日物品",value=text[:-2],inline=False)
        
        text = ""
        for item in self.weekly_item:
            text += f"{item.name_tw} {item.cost}\n"
        embed.add_field(name="每週物品",value=text[:-2],inline=False)
        embed.timestamp = datetime.now()
        embed.set_footer(text='更新時間')
        return embed

class ApexCraftingItem():
    def __init__(self,data):
        self.id = data.get('item')
        self.cost = data.get('cost')
        self.name = data.get('itemType').get('name')
        self.name_tw = jdict['ApexCraftingItem'].get(self.name,self.name)
        # self.rarity = data.get('itemType').get('rarity')
        # self.asset = data.get('itemType').get('asset')
        # self.rarityHex = data.get('itemType').get('rarityHex')

class ApexMapRotation():
    def __init__(self,data):
        try:
            self.nowmap = data["current"]['map']
            self.nowstart = datetime.strptime(data['current']['readableDate_start'],"%Y-%m-%d %H:%M:%S") + timedelta(hours=8)
            self.nowend = datetime.strptime(data['current']['readableDate_end'],"%Y-%m-%d %H:%M:%S") + timedelta(hours=8)
            self.remaining = data['current']['remainingTimer']
            self.mapimage = data['current']['asset']

            self.nextmap = data["next"]['map']
            self.nextstart = datetime.strptime(data['next']['readableDate_start'],"%Y-%m-%d %H:%M:%S") + timedelta(hours=8)
            self.nextend = datetime.strptime(data['next']['readableDate_end'],"%Y-%m-%d %H:%M:%S") + timedelta(hours=8)
        except TypeError:
            print(data)

    def desplay(self):
        tl = jdict['ApexMap']
        embed = BotEmbed.simple("Apex地圖輪替")
        embed.add_field(name="目前地圖",value=tl.get(self.nowmap,self.nowmap))
        embed.add_field(name="開始時間",value=self.nowstart)
        embed.add_field(name="結束時間",value=self.nowend)
        embed.add_field(name="下張地圖",value=tl.get(self.nextmap,self.nextmap))
        embed.add_field(name="開始時間",value=self.nextstart)
        embed.add_field(name="結束時間",value=self.nextend)
        embed.add_field(name="目前地圖剩餘時間",value=self.remaining)
        embed.set_image(url=self.mapimage)
        embed.timestamp = datetime.now()
        embed.set_footer(text='更新時間')
        return embed

class ApexStatus():
    def __init__(self,data):
        for i in data:
            print(i)
            for j in data[i]:
                print(j)

    def desplay(self):
        pass

class SteamUser():
    def __init__(self,data):
        self.id = data['steamid']
        self.name = data['personaname']
        self.profileurl = data['profileurl']
        self.avatar = data['avatarfull']
    
    def desplay(self):
        embed = BotEmbed.simple("Stean用戶資訊")
        embed.add_field(name="用戶名稱",value=self.name)
        embed.add_field(name="用戶id",value=self.id)
        embed.add_field(name="個人檔案連結",value='[點我]({0})'.format(self.profileurl))
        embed.set_thumbnail(url=self.avatar)
        return embed

class DBDPlayer(SteamUser):
    def __init__(self,data,name=None):
        #基本資料
        self.steamid = data["steamid"]
        self.name = name
        self.bloodpoints = data["bloodpoints"]
        self.survivor_rank = data["survivor_rank"]
        self.killer_rank = data["killer_rank"]
        self.killer_perfectgames = data["killer_perfectgames"]
        self.evilwithintierup = data["evilwithintierup"]
        
        #遊戲表現類
        self.cagesofatonement = data["cagesofatonement"]
        self.condemned = data["condemned"]
        self.sacrificed = data["sacrificed"]
        self.dreamstate = data["dreamstate"]
        self.rbtsplaced = data["rbtsplaced"]
        
        #命中、陷阱類
        self.blinkattacks = data["blinkattacks"]
        self.chainsawhits = data["chainsawhits"]
        self.shocked = data["shocked"]
        self.hatchetsthrown = data["hatchetsthrown"]
        self.lacerations = data["lacerations"]
        self.possessedchains = data["possessedchains"]
        self.lethalrushhits = data["lethalrushhits"]
        self.uncloakattacks = data["uncloakattacks"]
        self.beartrapcatches = data["beartrapcatches"]
        self.phantasmstriggered = data["phantasmstriggered"]

    def desplay(self):
        embed = BotEmbed.simple("DBD玩家資訊")
        embed.add_field(name="玩家名稱",value=self.name)
        embed.add_field(name="血點數",value=self.bloodpoints)
        embed.add_field(name="倖存者等級",value=self.survivor_rank)
        embed.add_field(name="殺手等級",value=self.killer_rank)
        embed.add_field(name="升階次數",value=self.evilwithintierup)
        embed.add_field(name="完美殺手場次",value=self.killer_perfectgames)

        embed.add_field(name="勞改次數",value=self.cagesofatonement)
        embed.add_field(name="詛咒次數",value=self.condemned)
        embed.add_field(name="獻祭次數",value=self.sacrificed)
        embed.add_field(name="送入夢境數",value=self.dreamstate)
        embed.add_field(name="頭套安裝數",value=self.rbtsplaced)
        
        embed.add_field(name="鬼影步命中",value=self.blinkattacks)
        embed.add_field(name="電鋸衝刺命中",value=self.chainsawhits)
        embed.add_field(name="電擊命中",value=self.shocked)
        embed.add_field(name="斧頭命中",value=self.hatchetsthrown)
        embed.add_field(name="飛刀命中",value=self.lacerations)
        embed.add_field(name="鎖鏈命中",value=self.possessedchains)
        embed.add_field(name="致命衝刺命中",value=self.lethalrushhits)
        embed.add_field(name="喪鐘襲擊",value=self.uncloakattacks)
        embed.add_field(name="陷阱捕捉",value=self.beartrapcatches)
        embed.add_field(name="汙泥陷阱觸發",value=self.phantasmstriggered)
        return embed