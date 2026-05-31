from datetime import datetime, timedelta
from functools import cached_property
from typing import Any, ClassVar

from pydantic import BaseModel, Field, model_validator

from starlib.fileDatabase import Jsondb
from starlib.utils import BotEmbed, convert_tz, nowtz

jdict = Jsondb.jdict


class RiotUser(BaseModel):
    puuid: str
    gameName: str
    tagLine: str

    @cached_property
    def fullname(self) -> str:
        return self.gameName + "#" + self.tagLine

    def embed(self):
        embed = BotEmbed.general(self.fullname)
        embed.add_field(name="puuid", value=self.puuid, inline=False)
        embed.timestamp = nowtz()
        return embed


class LOLPlayer(BaseModel):
    puuid: str
    profileIconId: int
    revisionDate: datetime
    summonerLevel: int

    @model_validator(mode="after")
    def __post_init__(self):
        self.revisionDate = convert_tz(self.revisionDate)
        return self

    def embed(self, name=None):
        embed = BotEmbed.general(name)
        embed.add_field(name="召喚師等級", value=self.summonerLevel, inline=False)
        embed.add_field(name="最後遊玩/修改資料時間", value=self.revisionDate.strftime("%Y/%m/%d %H:%M:%S"), inline=False)
        embed.add_field(name="puuid", value=self.puuid, inline=False)
        try:
            embed.set_thumbnail(url=f"https://ddragon.leagueoflegends.com/cdn/15.10.1/img/profileicon/{self.profileIconId}.png")
        except Exception:
            embed.set_thumbnail(url="https://i.imgur.com/B0TMreW.png")
        embed.set_footer(text="puuid是全球唯一的ID，不隨帳號移動地區而改變")

        return embed


class LOLMatchMetadata(BaseModel):
    dataVersion: str
    matchId: str
    participants: list[str]


class LOLPerks(BaseModel):
    statPerks: dict[str, int]
    styles: list[dict[str, Any]]


class LOLMissions(BaseModel):
    playerScore0: float = 0
    playerScore1: float = 0
    playerScore2: float = 0
    playerScore3: float = 0
    playerScore4: float = 0
    playerScore5: float = 0
    playerScore6: float = 0
    playerScore7: float = 0
    playerScore8: float = 0
    playerScore9: float = 0
    playerScore10: float = 0
    playerScore11: float = 0


class LOLChallenges(BaseModel):
    # 基本統計
    gameLength: float
    goldPerMinute: float
    damagePerMinute: float
    kda: float
    killParticipation: float
    teamDamagePercentage: float
    damageTakenOnTeamPercentage: float
    visionScorePerMinute: float

    # 擊殺相關
    kills: int = Field(alias="takedowns", default=0)
    soloKills: int = 0
    multikills: int = 0
    doubleKills: int = Field(alias="multikills", default=0)
    tripleKills: int = 0
    quadraKills: int = 0
    pentaKills: int = 0
    killingSprees: int = 0
    largestKillingSpree: int = 0

    # 傷害相關
    totalDamageDealt: int = 0
    totalDamageDealtToChampions: int = 0
    totalDamageTaken: int = 0
    bountyGold: float = 0

    # 技能相關
    abilityUses: int = 0
    skillshotsHit: int = 0
    skillshotsDodged: int = 0
    enemyChampionImmobilizations: int = 0

    # 其他統計
    laneMinionsFirst10Minutes: int = 0
    jungleCsBefore10Minutes: float = 0
    voidMonsterKill: int = 0
    turretTakedowns: int = 0
    baronTakedowns: int = 0
    dragonTakedowns: int = 0

    # 特殊成就
    flawlessAces: int = 0
    perfectGame: int = 0
    firstTurretKilled: int = 0

    # 其他字段可以用 Optional 處理
    HealFromMapSources: float | None = None
    snowballsHit: int | None = None

    class Config:
        extra = "allow"  # 允許額外字段，因為 challenges 包含很多可選字段


class LOLParticipant(BaseModel):
    # 基本信息
    participantId: int
    puuid: str
    riotIdGameName: str
    riotIdTagline: str
    summonerId: str
    summonerName: str = ""
    summonerLevel: int
    teamId: int

    # 角色信息
    championId: int
    championName: str
    championSkinId: int = 0
    championTransform: int = 0
    champLevel: int
    champExperience: int

    # 位置信息
    lane: str
    role: str
    teamPosition: str = ""
    individualPosition: str = "Invalid"

    # 遊戲統計
    kills: int
    deaths: int
    assists: int
    doubleKills: int = 0
    tripleKills: int = 0
    quadraKills: int = 0
    pentaKills: int = 0
    largestKillingSpree: int = 0
    largestMultiKill: int = 1
    killingSprees: int = 0

    # 傷害統計
    totalDamageDealt: int
    totalDamageDealtToChampions: int
    totalDamageTaken: int
    physicalDamageDealt: int
    physicalDamageDealtToChampions: int
    physicalDamageTaken: int
    magicDamageDealt: int
    magicDamageDealtToChampions: int
    magicDamageTaken: int
    trueDamageDealt: int
    trueDamageDealtToChampions: int
    trueDamageTaken: int
    largestCriticalStrike: int = 0

    # 經濟統計
    goldEarned: int
    goldSpent: int
    totalMinionsKilled: int
    neutralMinionsKilled: int = 0

    # 建築物統計
    turretKills: int = 0
    turretTakedowns: int = 0
    turretsLost: int = 0
    inhibitorKills: int = 0
    inhibitorTakedowns: int = 0
    inhibitorsLost: int = 0

    # 史詩怪物
    baronKills: int = 0
    dragonKills: int = 0

    # 物品
    item0: int = 0
    item1: int = 0
    item2: int = 0
    item3: int = 0
    item4: int = 0
    item5: int = 0
    item6: int = 0
    itemsPurchased: int = 0
    consumablesPurchased: int = 0

    # 召喚師技能
    summoner1Id: int
    summoner2Id: int
    summoner1Casts: int = 0
    summoner2Casts: int = 0

    # 技能施放
    spell1Casts: int = 0
    spell2Casts: int = 0
    spell3Casts: int = 0
    spell4Casts: int = 0

    # 視野和控制
    visionScore: int = 0
    wardsPlaced: int = 0
    wardsKilled: int = 0
    visionWardsBoughtInGame: int = 0
    sightWardsBoughtInGame: int = 0
    detectorWardsPlaced: int = 0
    timeCCingOthers: int = 0
    totalTimeCCDealt: int = 0

    # 治療和護盾
    totalHeal: int = 0
    totalHealsOnTeammates: int = 0
    totalUnitsHealed: int = 1
    totalDamageShieldedOnTeammates: int = 0

    # 時間統計
    timePlayed: int
    totalTimeSpentDead: int = 0
    longestTimeSpentLiving: int = 0

    # 遊戲結果
    win: bool
    gameEndedInEarlySurrender: bool = False
    gameEndedInSurrender: bool = False
    teamEarlySurrendered: bool = False

    # 特殊事件
    firstBloodKill: bool = False
    firstBloodAssist: bool = False
    firstTowerKill: bool = False
    firstTowerAssist: bool = False

    # Ping 統計
    allInPings: int = 0
    assistMePings: int = 0
    basicPings: int = 0
    commandPings: int = 0
    dangerPings: int = 0
    enemyMissingPings: int = 0
    enemyVisionPings: int = 0
    getBackPings: int = 0
    holdPings: int = 0
    needVisionPings: int = 0
    onMyWayPings: int = 0
    pushPings: int = 0
    retreatPings: int = 0
    visionClearedPings: int = 0

    # 複雜對象
    perks: LOLPerks
    challenges: LOLChallenges | None = None
    missions: LOLMissions

    # 其他
    profileIcon: int
    placement: int = 0
    playerSubteamId: int = 0
    subteamPlacement: int = 0
    eligibleForProgression: bool = True

    # 玩家增強（Arena 模式用）
    playerAugment1: int = 0
    playerAugment2: int = 0
    playerAugment3: int = 0
    playerAugment4: int = 0
    playerAugment5: int = 0
    playerAugment6: int = 0

    # 其他統計
    damageSelfMitigated: int = 0
    damageDealtToBuildings: int = 0
    damageDealtToObjectives: int = 0
    damageDealtToTurrets: int = 0
    nexusKills: int = 0
    nexusLost: int = 0
    nexusTakedowns: int = 0
    objectivesStolen: int = 0
    objectivesStolenAssists: int = 0
    totalAllyJungleMinionsKilled: int = 0
    totalEnemyJungleMinionsKilled: int = 0
    unrealKills: int = 0

    # 玩家評分相關
    PlayerScore0: float = 0
    PlayerScore1: float = 0
    PlayerScore2: float = 0
    PlayerScore3: float = 0
    PlayerScore4: float = 0
    PlayerScore5: float = 0
    PlayerScore6: float = 0
    PlayerScore7: float = 0
    PlayerScore8: float = 0
    PlayerScore9: float = 0
    PlayerScore10: float = 0
    PlayerScore11: float = 0

    def desplaytext(self):
        text = f"`{self.riotIdGameName}#{self.riotIdTagline}(LV. {self.summonerLevel})`\n"
        name = self.championName
        text += f"{name}(LV. {self.champLevel})\n"
        lane = self.lane
        if self.role != "NONE":
            lane += f" {self.role}"
        text += f"{lane}\n"
        kda = round((self.kills + self.assists) / self.deaths, 2) if self.deaths > 0 else (self.kills + self.assists)
        text += f"{self.kills}/{self.deaths}/{self.assists} KDA: {kda}\n"
        text += f"視野分：{self.visionScore} ({self.challenges.visionScorePerMinute}/min)\n"
        text += f"連殺：{self.doubleKills}/{self.tripleKills}/{self.quadraKills}/{self.pentaKills}\n"
        text += f"輸出：{self.totalDamageDealtToChampions} ({round(self.challenges.teamDamagePercentage * 100, 2)}%)\n"
        text += f"承受：{self.totalDamageTaken} ({round(self.challenges.damageTakenOnTeamPercentage * 100, 2)}%)\n"
        # text += f'治療/CC：{self.totalHeal}/{self.totalTimeCCDealt}\n'
        text += f"經濟：{self.goldEarned} ({round(self.challenges.goldPerMinute, 2)}/min)\n"
        text += f"吃兵：{self.totalMinionsKilled}\n"
        text += f"小龍/巴龍：{self.dragonKills}/{self.baronKills}\n"
        text += f"個人賞金：{self.challenges.bountyGold:.2f}\n"
        text += f"Ping問號燈：{self.enemyMissingPings}\n"

        if self.firstBloodKill and self.firstTowerKill:
            text += f"首殺+首塔🔪 "
        elif self.firstBloodKill:
            text += f"首殺🔪 "
        elif self.firstTowerKill:
            text += f"首塔🔪 "

        if self.gameEndedInEarlySurrender:
            text += f"提早投降🏳️"
        elif self.gameEndedInSurrender:
            text += f"投降🏳️"
        text += "\n"

        return text


class LOLObjective(BaseModel):
    first: bool
    kills: int


class LOLObjectives(BaseModel):
    atakhan: LOLObjective | None = None
    baron: LOLObjective
    champion: LOLObjective
    dragon: LOLObjective
    horde: LOLObjective
    inhibitor: LOLObjective
    riftHerald: LOLObjective
    tower: LOLObjective


class LOLFeat(BaseModel):
    featState: int


class LOLFeats(BaseModel):
    EPIC_MONSTER_KILL: LOLFeat
    FIRST_BLOOD: LOLFeat
    FIRST_TURRET: LOLFeat


class LOLTeam(BaseModel):
    teamId: int
    win: bool
    bans: list[Any] = []  # ARAM 模式通常沒有 ban
    objectives: LOLObjectives
    feats: LOLFeats | None = None


class LOLMatchInfo(BaseModel):
    endOfGameResult: str
    gameCreation: int  # 遊戲創建時間戳 (毫秒)
    gameDuration: int  # 遊戲持續時間 (秒)
    gameEndTimestamp: int  # 遊戲結束時間戳 (毫秒)
    gameId: int
    gameMode: str
    gameModeMutators: list[str] = []
    gameName: str
    gameStartTimestamp: int  # 遊戲開始時間戳 (毫秒)
    gameType: str
    gameVersion: str
    mapId: int
    participants: list[LOLParticipant]
    platformId: str
    queueId: int
    teams: list[LOLTeam]
    tournamentCode: str = ""


class LOLMatch(BaseModel):
    metadata: LOLMatchMetadata
    info: LOLMatchInfo

    def get_player_by_puuid(self, puuid: str) -> LOLParticipant | None:
        """根據 PUUID 獲取玩家資訊"""
        for participant in self.info.participants:
            if participant.puuid == puuid:
                return participant
        return None

    def get_player_by_name(self, summoner_name: str) -> LOLParticipant | None:
        """根據召喚師名稱獲取玩家資訊"""
        for participant in self.info.participants:
            if participant.riotIdGameName == summoner_name:
                return participant
        return None

    def get_team_participants(self, team_id: int) -> list[LOLParticipant]:
        """獲取指定隊伍的所有玩家"""
        return [p for p in self.info.participants if p.teamId == team_id]

    def get_winning_team(self) -> list[LOLParticipant]:
        """獲取獲勝隊伍的玩家"""
        return [p for p in self.info.participants if p.win]

    def get_losing_team(self) -> list[LOLParticipant]:
        """獲取失敗隊伍的玩家"""
        return [p for p in self.info.participants if not p.win]

    def desplay(self):
        embed = BotEmbed.simple("LOL對戰")
        gamemode = self.info.gameMode
        embed.add_field(name="遊戲模式", value=gamemode, inline=False)
        embed.add_field(name="對戰ID", value=self.metadata.matchId, inline=False)
        embed.add_field(name="遊戲版本", value=self.info.gameVersion, inline=False)
        minutes = str(self.info.gameDuration // 60)
        seconds = str(self.info.gameDuration % 60)
        time = f"{minutes}:{seconds}"
        embed.add_field(name="遊戲時長", value=time, inline=False)
        blue = ""
        red = ""
        i = 0
        for player in self.info.participants:
            if i < 5:
                blue += player.desplaytext()
                if i != 4:
                    blue += "\n"
            else:
                red += player.desplaytext()
                if i != 9:
                    red += "\n"
            i += 1
        if self.info.teams[0].win:
            embed.add_field(name="藍方👑", value=blue, inline=True)
            embed.add_field(name="紅方", value=red, inline=True)
        else:
            embed.add_field(name="藍方", value=blue, inline=True)
            embed.add_field(name="紅方👑", value=red, inline=True)
        return embed


class LOLRewardConfig(BaseModel):
    rewardValue: str
    rewardType: str
    maximumReward: int


class LOLSeasonMilestone(BaseModel):
    requireGradeCounts: dict[str, int]
    rewardMarks: int
    bonus: bool
    rewardConfig: LOLRewardConfig | None = None
    totalGamesRequires: int | None = None


class LOLChampionMastery(BaseModel):
    puuid: str
    championId: int
    championLevel: int
    championPoints: int
    lastPlayTime: datetime
    championPointsSinceLastLevel: int
    championPointsUntilNextLevel: int
    markRequiredForNextLevel: int
    tokensEarned: int
    championSeasonMilestone: int
    milestoneGrades: list[str] = Field(default_factory=list)
    nextSeasonMilestone: LOLSeasonMilestone


class LOLPlayerRank(BaseModel):
    leagueId: str = None
    queueType: str
    tier: str = None
    rank: str = None
    summonerId: str
    leaguePoints: int
    wins: int
    losses: int
    veteran: bool
    inactive: bool
    freshBlood: bool
    hotStreak: bool

    def embed(self):
        embed = BotEmbed.simple(self.queueType)
        embed.add_field(name="牌位", value=f"{self.tier} {self.rank}")
        embed.add_field(name="聯盟分數", value=self.leaguePoints)
        embed.add_field(name="勝敗", value=f"{self.wins}/{self.losses} {(round(self.wins / (self.wins + self.losses), 3)) * 100}%")
        return embed


class LOLActiveMatch:
    def __init__(self, data):
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
        gamemode = self.gameMode
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
        blue = ""
        red = ""
        i = 0
        for player in self.participants:
            if i < 5:
                blue += player.desplaytext()
                if i != 4:
                    blue += "\n"
            else:
                red += player.desplaytext()
                if i != 9:
                    red += "\n"
            i += 1
        embed.add_field(name="藍方", value=blue, inline=True)
        embed.add_field(name="紅方", value=red, inline=True)
        return embed


class LOLLActiveMatchPlayer:
    def __init__(self, data):
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
        text = f"`{self.summonerName}`\n"
        name = self.championName
        if not self.bot:
            text += f"{name}\n"
        else:
            text += f"{name}（機器人）\n"

        text += f"召喚師技能：{self.spell1Id}/{self.spell2Id}\n"
        text += f"主符文：{self.perkStyle}/{self.mainperk}\n"
        text += f"副符文：{self.perkSubStyle}\n"

        return text


class LOLBanChampion:
    __slots__ = [
        "championId",
        "teamId",
        "pickTurn",
        "name",
    ]

    def __init__(self, data):
        self.championId = data.get("championId")
        self.teamId = data.get("teamId")
        self.pickTurn = data.get("pickTurn")
        name = str(self.championId)
        self.name = name


class OsuPlayer:
    def __init__(self, data):
        self.name = data["username"]
        self.id = data["id"]
        self.global_rank = data["statistics"]["global_rank"]
        self.country_rank = data["statistics"]["country_rank"]
        self.pp = data["statistics"]["pp"]
        self.avatar_url = data["avatar_url"]
        self.country = data["country"]["code"]
        self.is_online = data["is_online"]
        self.level = data["statistics"]["level"]["current"]
        self.max_level = data["statistics"]["level"]["progress"]
        self.max_combo = data["statistics"]["maximum_combo"]
        # self.last_visit = datetime.datetime.strptime(data['last_visit'],"%Y-%m-%dT%H:%M:%S%Z")
        self.oragin_last_visit = datetime.strptime(data["last_visit"], "%Y-%m-%dT%H:%M:%S%z")
        self.e8_last_visit = self.oragin_last_visit + timedelta(hours=8)
        self.last_visit = self.e8_last_visit.strftime("%Y/%m/%d %H:%M:%S")
        self.url = f"https://osu.ppy.sh/users/{self.id}"

    def desplay(self, dc_user=None):
        embed = BotEmbed.general("Osu玩家資訊", url=self.url)
        embed.add_field(name="名稱", value=self.name)
        embed.add_field(name="id", value=self.id)
        embed.add_field(name="全球排名", value=self.global_rank)
        embed.add_field(name="地區排名", value=self.country_rank)
        embed.add_field(name="pp", value=self.pp)
        embed.add_field(name="國家", value=self.country)
        embed.add_field(name="等級", value=f"{self.level}({self.max_level}%)")
        embed.add_field(name="最多連擊數", value=self.max_combo)
        if self.is_online:
            embed.add_field(name="最後線上", value="Online")
        else:
            embed.add_field(name="最後線上", value=self.last_visit)
        embed.set_thumbnail(url=self.avatar_url)
        return embed


class OsuBeatmap:
    def __init__(self, data):
        self.id = data["id"]
        self.beatmapset_id = data["beatmapset_id"]
        self.mode = data["mode"]
        self.status = data["status"]
        self.url = data["url"]
        self.time = data["total_length"]
        self.title = data["beatmapset"]["title"]
        self.cover = data["beatmapset"]["covers"]["cover"]
        self.max_combo = data["max_combo"]
        self.pass_rate = round(data["passcount"] / data["playcount"], 3)
        self.checksum = data["checksum"]
        self.bpm = data["bpm"]
        self.star = data["difficulty_rating"]
        self.ar = data["ar"]
        self.cs = data["cs"]
        self.od = data["accuracy"]
        self.hp = data["drain"]
        self.version = data["version"]

    def desplay(self):
        embed = BotEmbed.simple(title="Osu圖譜資訊")
        embed.add_field(name="名稱", value=self.title)
        embed.add_field(name="歌曲長度(秒)", value=self.time)
        embed.add_field(name="星數", value=self.star)
        embed.add_field(name="模式", value=self.mode)
        embed.add_field(name="combo數", value=self.max_combo)
        embed.add_field(name="圖譜狀態", value=self.status)
        embed.add_field(name="圖譜id", value=self.id)
        embed.add_field(name="圖譜組id", value=self.beatmapset_id)
        embed.add_field(name="通過率", value=self.pass_rate)
        embed.add_field(name="BPM", value=self.bpm)
        embed.add_field(name="網址", value="[點我]({0})".format(self.url))
        embed.set_image(url=self.cover)
        return embed


class OsuMultiplayer:
    def __init__(self, data):
        print(data)


class ApexPlayer:
    def __init__(self, data):
        # basic information
        self.name = data["global"]["name"]
        self.id = data["global"]["uid"]
        self.platform = data["global"]["platform"]
        self.level = data["global"]["level"]
        self.avatar = data["global"]["avatar"]
        # bans
        self.bans = data["global"]["bans"]
        # rank
        self.rank = data["global"]["rank"]["rankName"]
        if data["global"]["rank"]["rankName"] != "Unranked":
            self.rank += " " + str(data["global"]["rank"]["rankDiv"])
        self.rank_score = data["global"]["rank"]["rankScore"]
        self.arena_rank = data["global"]["arena"]["rankName"]
        if data["global"]["arena"]["rankName"] != "Unranked":
            self.arena_rank += " " + str(data["global"]["arena"]["rankDiv"])
        self.arena_score = data["global"]["arena"]["rankScore"]
        # state
        self.now_state = data["realtime"]["currentStateAsText"]
        # selected
        self.legends_selected_name = data["legends"]["selected"]["LegendName"]
        self.legends_selected_tacker = data["legends"]["selected"]["data"]
        self.legends_selected_banner = data["legends"]["selected"]["ImgAssets"]["banner"].replace(" ", "%20")

    def desplay(self, dc_user=None):
        embed = BotEmbed.simple("Apex玩家資訊")
        embed.add_field(name="名稱", value=self.name)
        embed.add_field(name="id", value=self.id)
        embed.add_field(name="平台", value=self.platform)
        embed.add_field(name="等級", value=self.level)
        embed.add_field(name="牌位階級", value=self.rank)
        embed.add_field(name="牌位分數", value=self.rank_score)
        embed.add_field(name="競技場牌位階級", value=self.arena_rank)
        embed.add_field(name="競技場牌位分數", value=self.arena_score)
        embed.add_field(name="目前狀態", value=self.now_state)
        if self.bans["isActive"]:
            embed.add_field(name="目前ban狀態", value=self.bans["remainingSeconds"])
        else:
            embed.add_field(name="目前ban狀態", value=self.bans["isActive"])
        embed.add_field(name="目前選擇角色", value=self.legends_selected_name)
        embed.set_image(url=self.legends_selected_banner)
        return embed

class MapData(BaseModel):
    start: datetime
    end: datetime
    readableDate_start: str
    readableDate_end: str
    map: str
    code: str
    DurationInSecs: int
    DurationInMinutes: int
    asset: str | None = None
    remainingSecs: int | None = None
    remainingMins: int | None = None
    remainingTimer: str | None = None

    @model_validator(mode="after")
    def __post_init__(self):
        self.start = convert_tz(self.start)
        self.end = convert_tz(self.end)
        return self


class LTMMapData(MapData):
    isActive: bool | None = None
    eventName: str | None = None


class RotationType(BaseModel):
    current: MapData | LTMMapData
    next: MapData | LTMMapData


class ApexMapRotation(BaseModel):
    battle_royale: RotationType
    ranked: RotationType | None = None
    ltm: RotationType

    def embeds(self):
        tl: dict = jdict["ApexMap"]
        event_tl: dict = jdict["ApexEvent"]
        now = nowtz()
        lst = list()
        if self.ranked is not None:
            embed_rank = BotEmbed.simple("Apex地圖：積分")
            embed_rank.add_field(name="目前地圖", value=tl.get(self.ranked.current.map, self.ranked.current.map))
            embed_rank.add_field(name="開始時間", value=self.ranked.current.start.strftime("%Y/%m/%d %H:%M"))
            embed_rank.add_field(name="結束時間", value=self.ranked.current.end.strftime("%Y/%m/%d %H:%M"))
            embed_rank.add_field(name="下張地圖", value=tl.get(self.ranked.next.map, self.ranked.next.map))
            embed_rank.add_field(name="開始時間", value=self.ranked.next.start.strftime("%Y/%m/%d %H:%M"))
            embed_rank.add_field(name="結束時間", value=self.ranked.next.end.strftime("%Y/%m/%d %H:%M"))
            embed_rank.add_field(name="目前地圖剩餘時間", value=self.ranked.current.remainingTimer)
            embed_rank.set_image(url=self.ranked.current.asset)
            embed_rank.timestamp = now
            embed_rank.set_footer(text="更新時間")
            lst.append(embed_rank)

        embed_battle_royale = BotEmbed.simple("Apex地圖：大逃殺")
        embed_battle_royale.add_field(name="目前地圖", value=tl.get(self.battle_royale.current.map, self.battle_royale.current.map))
        embed_battle_royale.add_field(name="開始時間", value=self.battle_royale.current.start.strftime("%Y/%m/%d %H:%M"))
        embed_battle_royale.add_field(name="結束時間", value=self.battle_royale.current.end.strftime("%Y/%m/%d %H:%M"))
        embed_battle_royale.add_field(name="下張地圖", value=tl.get(self.battle_royale.next.map, self.battle_royale.next.map))
        embed_battle_royale.add_field(name="開始時間", value=self.battle_royale.next.start.strftime("%Y/%m/%d %H:%M"))
        embed_battle_royale.add_field(name="結束時間", value=self.battle_royale.next.end.strftime("%Y/%m/%d %H:%M"))
        embed_battle_royale.add_field(name="目前地圖剩餘時間", value=self.battle_royale.current.remainingTimer)
        embed_battle_royale.set_image(url=self.battle_royale.current.asset)
        embed_battle_royale.timestamp = now
        embed_battle_royale.set_footer(text="更新時間")
        lst.append(embed_battle_royale)

        embed_ltm = BotEmbed.simple(f"Apex地圖：限時模式")
        embed_ltm.add_field(
            name="目前地圖",
            value=f"{event_tl.get(self.ltm.current.eventName, self.ltm.current.eventName)}：{tl.get(self.ltm.current.map, self.ltm.current.map)}",
        )
        embed_ltm.add_field(name="開始時間", value=self.ltm.current.start.strftime("%Y/%m/%d %H:%M"))
        embed_ltm.add_field(name="結束時間", value=self.ltm.current.end.strftime("%Y/%m/%d %H:%M"))
        embed_ltm.add_field(
            name="下張地圖", value=f"{event_tl.get(self.ltm.next.eventName, self.ltm.next.eventName)}：{tl.get(self.ltm.next.map, self.ltm.next.map)}"
        )
        embed_ltm.add_field(name="開始時間", value=self.ltm.next.start.strftime("%Y/%m/%d %H:%M"))
        embed_ltm.add_field(name="結束時間", value=self.ltm.next.end.strftime("%Y/%m/%d %H:%M"))
        embed_ltm.add_field(name="目前地圖剩餘時間", value=self.ltm.current.remainingTimer)
        embed_ltm.set_image(url=self.ltm.current.asset)
        embed_ltm.timestamp = now
        embed_ltm.set_footer(text="更新時間")
        lst.append(embed_ltm)

        return lst


class ApexStatus:
    def __init__(self, data):
        for i in data:
            print(i)
            for j in data[i]:
                print(j)

    def embed(self):
        pass


class SteamUser(BaseModel):
    _PERSONA_STATES: ClassVar[dict] = {0: "離線", 1: "線上", 2: "忙碌", 3: "離開", 4: "打瞌睡", 5: "尋求交易", 6: "尋求遊玩"}
    _VISIBILITY_STATES: ClassVar[dict] = {1: "私密", 2: "好友可見", 3: "公開"}

    steamid: str
    communityvisibilitystate: int
    profilestate: int
    personaname: str
    profileurl: str
    avatar: str
    avatarmedium: str
    avatarfull: str
    avatarhash: str
    lastlogoff: int
    personastate: int
    primaryclanid: str
    timecreated: int
    personastateflags: int
    loccountrycode: str | None = None

    def embed(self):
        embed = BotEmbed.simple(self.personaname)
        embed.add_field(name="用戶id", value=self.steamid)
        embed.add_field(name="個人檔案連結", value=f"[點我]({self.profileurl})")
        embed.add_field(name="帳號狀態", value=self._get_persona_state(), inline=True)
        embed.add_field(name="可見性", value=self._get_visibility_state(), inline=True)
        if self.loccountrycode:
            embed.add_field(name="國家", value=self.loccountrycode)
        embed.add_field(name="帳號建立時間", value=f"<t:{self.timecreated}>", inline=False)
        embed.add_field(name="最後離線時間", value=f"<t:{self.lastlogoff}>", inline=False)
        embed.set_thumbnail(url=self.avatarfull)
        return embed

    def _get_persona_state(self) -> str:
        """將 personastate 轉換為可讀的狀態"""
        return self._PERSONA_STATES.get(self.personastate, "未知")

    def _get_visibility_state(self) -> str:
        """將 communityvisibilitystate 轉換為可讀的可見性"""
        return self._VISIBILITY_STATES.get(self.communityvisibilitystate, "未知")


class SteamGame(BaseModel):
    appid: int
    name: str | None = None
    img_icon_url: str | None = None
    has_community_visible_stats: bool | None = None
    playtime_forever: int
    playtime_windows_forever: int
    playtime_mac_forever: int
    playtime_linux_forever: int
    playtime_deck_forever: int
    content_descriptorids: list[int] | None = None
    rtime_last_played: datetime
    playtime_disconnected: int


class SteamOwnedGame(BaseModel):
    game_count: int
    games: list[SteamGame]


class DBDPlayer(BaseModel):
    steamid: str
    name: str
    bloodpoints: int
    survivor_rank: int
    killer_rank: int
    killer_perfectgames: int
    evilwithintierup: int

    # 遊戲表現類
    cagesofatonement: int
    condemned: int
    sacrificed: int
    dreamstate: int
    rbtsplaced: int

    # 命中、陷阱類
    blinkattacks: int
    chainsawhits: int
    shocked: int
    hatchetsthrown: int
    lacerations: int
    possessedchains: int
    lethalrushhits: int
    uncloakattacks: int
    beartrapcatches: int
    phantasmstriggered: int

    def embed(self):
        embed = BotEmbed.simple("DBD玩家資訊")
        embed.add_field(name="玩家名稱", value=self.name)
        embed.add_field(name="血點數", value=self.bloodpoints)
        embed.add_field(name="倖存者等級", value=self.survivor_rank)
        embed.add_field(name="殺手等級", value=self.killer_rank)
        embed.add_field(name="升階次數", value=self.evilwithintierup)
        embed.add_field(name="完美殺手場次", value=self.killer_perfectgames)

        embed.add_field(name="勞改次數", value=self.cagesofatonement)
        embed.add_field(name="詛咒次數", value=self.condemned)
        embed.add_field(name="獻祭次數", value=self.sacrificed)
        embed.add_field(name="送入夢境數", value=self.dreamstate)
        embed.add_field(name="頭套安裝數", value=self.rbtsplaced)

        embed.add_field(name="鬼影步命中", value=self.blinkattacks)
        embed.add_field(name="電鋸衝刺命中", value=self.chainsawhits)
        embed.add_field(name="電擊命中", value=self.shocked)
        embed.add_field(name="斧頭命中", value=self.hatchetsthrown)
        embed.add_field(name="飛刀命中", value=self.lacerations)
        embed.add_field(name="鎖鏈命中", value=self.possessedchains)
        embed.add_field(name="致命衝刺命中", value=self.lethalrushhits)
        embed.add_field(name="喪鐘襲擊", value=self.uncloakattacks)
        embed.add_field(name="陷阱捕捉", value=self.beartrapcatches)
        embed.add_field(name="汙泥陷阱觸發", value=self.phantasmstriggered)
        return embed


class MojangUser(BaseModel):
    id: str
    name: str
