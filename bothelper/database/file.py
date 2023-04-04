import json

class JsonDatabase():
    def __init__(self):
        """
        CWB = 中央氣象局

        TRN = tracker.gg
        """
        self.location = "./database"
        self.data_location = "./data"
        self.__dict = {
            'lol_jdict': f'{self.data_location}/lol_dict.json',
            'jdict': f'{self.data_location}/dict.json',
            'jdata': f'{self.location}/setting.json',
            'cdata': f'{self.location}/channel_settings.json',
            'picdata': f'{self.data_location}/bot_settings/picture.json',
            'udata': f'{self.location}/user_settings/basic.json',
            'jpt': f'{self.location}/user_settings/point.json',
            'jloot': f'{self.location}/lottery.json',
            'bet_data': f'{self.location}/bet.json',
            'gdata': f'{self.location}/gamer_data.json',
            'jdsign': f'{self.location}/sign_day.json',
            'jwsign': f'{self.location}/sign_week.json',
            'jevent': f'{self.location}/bot_settings/event.json',
            'rsdata': f'{self.location}/role_save.json',
            'jpet': f'{self.location}/user_settings/pet.json',
            'jbag': f'{self.location}/user_settings/bag.json',
            'cache': f'{self.location}/cache.json',
            'monster_basic': f'{self.data_location}/RPG_settings/monster_basic.json',
            'jRcoin': f'{self.location}/user_settings/rcoin.json',
            'jhoyo': f'{self.location}/game_settings/hoyo.json',
            'jtwitch': f'{self.location}/community_settings/twitch.json',
        }
        self.lol_jdict = json.load(open(self.__dict['lol_jdict'],mode='r',encoding='utf8'))
        self.jdict = json.load(open(self.__dict['jdict'],mode='r',encoding='utf8'))
        self.jdata = json.load(open(self.__dict['jdata'],mode='r',encoding='utf8'))
        #self.cdata = json.load(open(self.__dict['cdata'],mode='r',encoding='utf8'))
        self.picdata = json.load(open(self.__dict['picdata'],mode='r',encoding='utf8'))
        #self.udata = json.load(open(self.__dict['udata'],'r',encoding='utf8'))
        #self.jpt = json.load(open(self.__dict['jpt'],mode='r',encoding='utf8'))
        #self.jloot = json.load(open(self.__dict['jloot'],mode='r',encoding='utf8'))
        #self.bet_data = json.load(open(self.__dict['bet_data'],mode='r',encoding='utf8'))
        #self.gdata = json.load(open(self.__dict['gdata'],'r',encoding='utf8'))
        #self.jdsign = json.load(open(self.__dict['jdsign'],mode='r',encoding='utf8'))
        #self.jwsign = json.load(open(self.__dict['jwsign'],mode='r',encoding='utf8'))
        #self.jevent = json.load(open(self.__dict['jevent'],mode='r',encoding='utf8'))
        #self.rsdata = json.load(open(self.__dict['rsdata'],mode='r',encoding='utf8'))
        #self.jpet = json.load(open(self.__dict['jpet'],mode='r',encoding='utf8'))
        #self.jbag = json.load(open(self.__dict['jbag'],mode='r',encoding='utf8'))
        self.cache = json.load(open(self.__dict['cache'],mode='r',encoding='utf8'))
        #self.monster_basic = json.load(open(self.__dict['monster_basic'],mode='r',encoding='utf8'))
        #self.jRcoin = json.load(open(self.__dict['jRcoin'],mode='r',encoding='utf8'))
        #self.jhoyo = json.load(open(self.__dict['jhoyo'],mode='r',encoding='utf8'))
        #self.jtwitch = json.load(open(self.__dict['jtwitch'],mode='r',encoding='utf8'))
        self.tokens = json.load(open(f'{self.location}/token.json',mode='r',encoding='utf8'))

    def write(self,file:str,data:dict):
        try:
            location = self.__dict[file]
            with open(file=location,mode='w',encoding='utf8') as jfile:
                json.dump(data,jfile,indent=4,ensure_ascii=False)
        except:
            raise KeyError("此項目沒有在資料庫中")

    def get_token(self,webname:str):
        """獲取相關api的tokens
        
        支援CWB_api,osu(id,secret),TRN,apex,steam,twitch(id,secret),twitch_chatbot,youtube,riot,openai
        """
        dict = {
            "CWB_api":'CWB_api',
            'osu':'osu_api',
            'TRN':'TRN_API',
            'apex':'apex_status_API',
            'steam':'steam_api',
            'twitch':'twitch_api',
            'youtube':'youtube_api',
            'riot':"riot_api",
            'openai':'openai_api',
            'twitch_chatbot':'twitch_chatbot'
            }
        if webname in dict:
            name = dict[webname]
            return self.tokens[name]
        else:
            raise ValueError('無此API token')

    # @staticmethod
    # async def get_gamedata(user_id:str, game:str, ctx:discord.ApplicationContext=None):
    #     """查詢資料庫中的玩家資訊，若輸入dc用戶則需傳入ctx\n
    #     dcuser and in database -> 資料庫資料\n
    #     dcuser and not in database -> None\n
    #     not dcuser -> user_id(原資料輸出)
    #     """
    #     gdata = JsonDatabase().gdata
        
    #     if ctx:
    #         dcuser = await find.user2(ctx,user_id)
    #         if dcuser:
    #             user_id = str(dcuser.id)
    #         else:
    #             return user_id
    #     else:
    #         user_id = str(user_id)

    #     try:
    #         data = gdata[str(user_id)][game]
    #         if game in ['steam']:
    #             data = data['id']
    #         return data
    #     except:
    #         return None

class CsvDatabase:
    pass

class XmlDatabase:
    pass