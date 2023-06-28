import json

class JsonDatabase():
    def __init__(self):
        """
        CWB = 中央氣象局

        TRN = tracker.gg
        """
        self.db_location = "./database"
        self.data_location = "./data"
        self.__dict = {
            'lol_jdict': f'{self.data_location}/lol_dict.json',
            'jdict': f'{self.data_location}/dict.json',
            'jdata': f'{self.db_location}/setting.json',
            #'cdata': f'{self.location}/channel_settings.json',
            'picdata': f'{self.data_location}/bot_settings/picture.json',
            #'udata': f'{self.location}/user_settings/basic.json',
            #'jpt': f'{self.location}/user_settings/point.json',
            #'jloot': f'{self.location}/lottery.json',
            #'bet_data': f'{self.location}/bet.json',
            #'gdata': f'{self.location}/gamer_data.json',
            #'jdsign': f'{self.location}/sign_day.json',
            #'jwsign': f'{self.location}/sign_week.json',
            #'jevent': f'{self.location}/bot_settings/event.json',
            #'rsdata': f'{self.location}/role_save.json',
            #'jpet': f'{self.location}/user_settings/pet.json',
            #'jbag': f'{self.location}/user_settings/bag.json',
            'cache': f'{self.db_location}/cache.json',
            #'monster_basic': f'{self.data_location}/RPG_settings/monster_basic.json',
            #'jRcoin': f'{self.location}/user_settings/rcoin.json',
            #'jhoyo': f'{self.location}/game_settings/hoyo.json',
            #'jtwitch': f'{self.location}/community_settings/twitch.json',
            'tokens': f'{self.db_location}/token.json'
        }
        for file in self.__dict:
            setattr(self, file,json.load(open(self.__dict[file],mode='r',encoding='utf8')))

    def write(self,file:str,data:dict):
        try:
            location = self.__dict[file]
            setattr(self,file,data)
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
        
    def read_cache(self,key):
        """讀取cache的指定資料"""
        return self.cache.get(key)
    
    def write_cache(self,key,value):
        """將指定資料寫入cache並更新內容"""
        with open(f'{self.location}/cache.json','w',encoding="utf-8") as jfile:
            self.cache[key] = value
            json.dump(self.cache,jfile,indent=4,ensure_ascii=False)

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