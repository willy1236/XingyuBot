import json,os
from typing import TYPE_CHECKING

class JsonDatabase():
    if TYPE_CHECKING:
        lol_jdict: dict
        jdict: dict
        jdata: dict
        picdata: dict
        cache: dict
        tokens: dict
        channel_dict: dict
        dynamic_voice_list: list

    __slots__ = [
        "_DBPATH",
        "_dict",
        "lol_jdict",
        "jdict",
        "jdata",
        "picdata",
        "cache",
        "tokens",
    ]

    def __init__(self,create_file=True):
        """
        CWB = 中央氣象局

        TRN = tracker.gg
        """
        self._DBPATH = "./database"
        self._dict = {
            'lol_jdict': f'{self._DBPATH}/lol_dict.json',
            'jdict': f'{self._DBPATH}/dict.json',
            'jdata': f'{self._DBPATH}/setting.json',
            #'cdata': f'{self.location}/channel_settings.json',
            'picdata': f'{self._DBPATH}/picture.json',
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
            'cache': f'{self._DBPATH}/cache.json',
            #'monster_basic': f'{self.data_location}/RPG_settings/monster_basic.json',
            #'jRcoin': f'{self.location}/user_settings/rcoin.json',
            #'jhoyo': f'{self.location}/game_settings/hoyo.json',
            #'jtwitch': f'{self.location}/community_settings/twitch.json',
            'tokens': f'{self._DBPATH}/token.json'
        }
        if not os.path.isdir(self._DBPATH):
            os.mkdir(self._DBPATH)
        
        for file in self._dict:
            if not os.path.isfile(self._dict[file]):
                if not create_file:
                    continue
                with open(self._dict[file],'w',encoding='utf-8') as jfile:
                    json.dump({},jfile,indent=4)
                    print(f">> Created json file: {file} <<")
            
            with open(self._dict[file],mode='r',encoding='utf8') as jfile:
                setattr(self, file,json.load(jfile))


    def write(self,file:str,data:dict):
        try:
            location = self._dict[file]
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
            token =  self.tokens[webname]
            if token:
                return token
            else:
                raise ValueError('無此API token')
        
    def read_cache(self,key):
        """讀取cache的指定資料"""
        return self.cache.get(key)
    
    def write_cache(self,key,value):
        """將指定資料寫入cache並更新內容"""
        with open(f'{self._DBPATH}/cache.json','w',encoding="utf-8") as jfile:
            self.cache[key] = value
            json.dump(self.cache,jfile,indent=4,ensure_ascii=False)

    def get_jdict(self,key,value):
        """取得jdict資料"""
        return self[key].get(value,value)
        

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