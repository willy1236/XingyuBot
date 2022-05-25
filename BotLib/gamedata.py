import requests,datetime
from BotLib.database import Database
from BotLib.basic import BotEmbed

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
        embed = BotEmbed.simple("Osu玩家資訊")
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


class ApexPlayer():
    def __init__(self,data):
        self.username = data['global']['name']
        self.id = data['global']['uid']
        self.platform = data['global']['platform']
        self.level = data['global']['level']
        self.avatar = data['global']['avatar']
        
        self.bans = data['global']['bans']

        self.rank = data['global']['rank']['rankName']
        if data['global']['rank']['rankName'] != "Unranked":
            self.rank += " "+str(data['global']['rank']['rankDiv'])
        self.rank_score = data['global']['rank']['rankScore']
        self.arena_rank = data['global']['arena']['rankName']
        if data['global']['arena']['rankName'] != "Unranked":
            self.arena_rank += " "+str(data['global']['arena']['rankDiv'])
        self.arena_score = data['global']['arena']['rankScore']
        
        self.now_state =  data['realtime']['currentStateAsText']

        self.desplay = self.embed()

    def embed(self):
        embed = BotEmbed.simple("Apex玩家資訊")
        embed.add_field(name="名稱",value=self.username)
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
        embed.set_image(url=self.avatar)
        return embed

class ApexCrafting():
    def __init__(self,data):
        self.daily = data[0]
        self.weekly = data[1]

        self.daily_start = self.daily['startDate']
        self.daily_end = self.daily['endDate']
        self.item1 = self.daily['bundleContent'][0]
        self.item1_cost = self.item1['cost']
        self.item1_name = self.item1['itemType']['name']
        self.item1_id = self.item1['item']
        self.item2 = self.daily['bundleContent'][1]
        self.item2_cost = self.item2['cost']
        self.item2_name = self.item2['itemType']['name']
        self.item2_id = self.item2['item']

        self.weekly_start = self.weekly['startDate']
        self.weekly_end = self.weekly['endDate']
        self.item3 = self.weekly['bundleContent'][0]
        self.item3_cost = self.item3['cost']
        self.item3_name = self.item3['itemType']['name']
        self.item3_id = self.item3['item']
        self.item4 = self.weekly['bundleContent'][1]
        self.item4_cost = self.item4['cost']
        self.item4_name = self.item4['itemType']['name']
        self.item4_id = self.item4['item']

        self.desplay = self.embed()
    
    def embed(self):
        embed = BotEmbed.simple("Apex合成器內容")
        dict = {
            "extended_light_mag":"紫色輕型彈匣",
            "backpack":"紫色背包",
            "helmet":"紫色頭盔",
            "optic_cq_hcog_bruiser":"2倍鏡",
            "optic_hcog_ranger":"3倍鏡",
            "shatter_caps":"粉碎蓋",
            "extended_energy_mag":"紫色能量彈匣",
            "optic_digital_threat":"1x數位威脅",
            "knockdown_shield":"紫色擊倒護盾",
            "mobile_respawn_beacon":"行動重生台",
            "shotgun_bolt":"紫色霰彈槍栓",
            "hammerpoint_rounds":"椎點彈藥",
            "extended_heavy_mag":"紫色重型彈匣",
            "optic_hcog_bruiser":"optic_hcog_bruiser"
        }
        item_name = []
        item_name.append(dict.get(self.item1_name,self.item1_name))
        item_name.append(dict.get(self.item2_name,self.item2_name))
        item_name.append(dict.get(self.item3_name,self.item3_name))
        item_name.append(dict.get(self.item4_name,self.item4_name))

        embed.add_field(name="每日物品1",value=item_name[0],inline=False)
        embed.add_field(name="每日物品1價格",value=self.item1_cost,inline=False)
        embed.add_field(name="每日物品2",value=item_name[1],inline=False)
        embed.add_field(name="每日物品2價格",value=self.item2_cost,inline=False)
        embed.add_field(name="每週物品1",value=item_name[2],inline=False)
        embed.add_field(name="每週物品1價格",value=self.item3_cost,inline=False)
        embed.add_field(name="每週物品2",value=item_name[3],inline=False)
        embed.add_field(name="每週物品2價格",value=self.item4_cost,inline=False)
        embed.timestamp = datetime.datetime.now()
        embed.set_footer(text='更新時間')
        return embed

class ApexMapRotation():
    def __init__(self,data):
        self.nowmap = data["current"]['map']
        self.nowstart = datetime.datetime.strptime(data['current']['readableDate_start'],"%Y-%m-%d %H:%M:%S")+datetime.timedelta(hours=8)
        self.nowend = datetime.datetime.strptime(data['current']['readableDate_end'],"%Y-%m-%d %H:%M:%S")+datetime.timedelta(hours=8)
        self.remaining = data['current']['remainingTimer']
        self.mapimage = data['current']['asset']

        self.nextmap = data["next"]['map']
        self.nextstart = datetime.datetime.strptime(data['next']['readableDate_start'],"%Y-%m-%d %H:%M:%S")+datetime.timedelta(hours=8)
        self.nextend = datetime.datetime.strptime(data['next']['readableDate_end'],"%Y-%m-%d %H:%M:%S")+datetime.timedelta(hours=8)

        self.desplay = self.embed()

    def embed(self):
        dict = {
            "Storm Point":"風暴點",
            "Olympus":"奧林匹斯",
            "World's Edge":"世界邊緣"
        }
        embed = BotEmbed.simple("Apex地圖輪替")
        embed.add_field(name="目前地圖",value=dict.get(self.nowmap,self.nowmap))
        embed.add_field(name="開始時間",value=self.nowstart)
        embed.add_field(name="結束時間",value=self.nowend)
        embed.add_field(name="下張地圖",value=dict.get(self.nextmap,self.nextmap))
        embed.add_field(name="開始時間",value=self.nextstart)
        embed.add_field(name="結束時間",value=self.nextend)
        embed.add_field(name="目前地圖剩餘時間",value=self.remaining)
        embed.set_image(url=self.mapimage)
        embed.timestamp = datetime.datetime.now()
        embed.set_footer(text='更新時間')
        return embed

class ApexStatus():
    def __init__(self,data):
        print(data)

class DBDPlayer():
    def __init__(self,data):
        #基本資料
        self.id = data["id"]
        self.name = SteamData().get_user(self.id).name
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

        self.desplay = self.embed()
    
    def embed(self):
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
        
class SteamUser():
    def __init__(self,data):
        self.id = data['steamid']
        self.name = data['personaname']
        self.profileurl = data['profileurl']
        self.avatar = data['avatarfull']
        self.desplay = self.embed()
    
    def embed(self):
        embed = BotEmbed.simple("Stean用戶資訊")
        embed.add_field(name="用戶名稱",value=self.name)
        embed.add_field(name="用戶id",value=self.id)
        embed.add_field(name="個人檔案連結",value='[點我]({0})'.format(self.profileurl))
        embed.set_thumbnail(url=self.avatar)
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

# class ApexData():
#     def __init__(self):
#         self.headers = {
#         'TRN-Api-Key': Database().TRN_API,
#         'Accept': 'application/json',
#         'Accept-Encoding': 'gzip'
#         }
    
#     def get_player(self,user):
#         if user:
#             response = requests.get(f'https://public-api.tracker.gg/v2/apex/standard/profile/origin/{user}', headers=self.headers)
#             data = response.json().get('data')
#             return ApexPlayer(data)
#         else:
#             return None

class ApexData():
    def __init__(self):
        pass

    def get_player(self,user):
        try:
            response = requests.get(f'https://api.mozambiquehe.re/bridge?auth={Database().apex_status_API}&player={user}&platform=PC').json()
            return ApexPlayer(response)
        except:
            return None
    
    def get_crafting():
        response = requests.get(f'https://api.mozambiquehe.re/crafting?auth={Database().apex_status_API}').json()
        return ApexCrafting(response)
    
    def get_map_rotation():
        response = requests.get(f'https://api.mozambiquehe.re/maprotation?auth={Database().apex_status_API}').json()
        return ApexMapRotation(response)

    def get_status():
        response = requests.get(f'https://api.mozambiquehe.re/servers?auth={Database().apex_status_API}').json()
        return ApexStatus(response)

class DBDData():
    def __init__(self):
        pass

    def get_player(self,user):
        try:
            response = requests.get(f'https://dbd.onteh.net.au/api/playerstats?id={user}').json()
            return DBDPlayer(response)
        except:
            return None

class SteamData():
    def __init__(self):
        pass

    def get_user(self,user):
        response = requests.get(f'https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/?key={Database().steam_api}&steamids={user}')
        if response.status_code == 200:
            APIdata = response.json().get('response').get('players')[0]
            return SteamUser(APIdata)
        else:
            return None