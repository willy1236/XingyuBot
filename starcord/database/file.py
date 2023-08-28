import json,os,csv
import pandas as pd
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
        "_db_location",
        "_dict",
        "lol_jdict",
        "jdict",
        "jdata",
        "picdata",
        "cache",
        "tokens",
        "channel_dict",
        "dynamic_voice_list",
    ]

    def __init__(self,create_file=True):
        """
        CWB = 中央氣象局

        TRN = tracker.gg
        """
        self._db_location = "./database"
        self._dict = {
            'lol_jdict': f'{self._db_location}/lol_dict.json',
            'jdict': f'{self._db_location}/dict.json',
            'jdata': f'{self._db_location}/setting.json',
            #'cdata': f'{self.location}/channel_settings.json',
            'picdata': f'{self._db_location}/picture.json',
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
            'cache': f'{self._db_location}/cache.json',
            #'monster_basic': f'{self.data_location}/RPG_settings/monster_basic.json',
            #'jRcoin': f'{self.location}/user_settings/rcoin.json',
            #'jhoyo': f'{self.location}/game_settings/hoyo.json',
            #'jtwitch': f'{self.location}/community_settings/twitch.json',
            'tokens': f'{self._db_location}/token.json'
        }
        if not os.path.isdir(self._db_location):
            os.mkdir(self._db_location)
        
        for file in self._dict:
            if not os.path.isfile(self._dict[file]):
                if not create_file:
                    continue
                with open(self._dict[file],'w',encoding='utf-8') as jfile:
                    json.dump({},jfile,indent=4)
                    print(f">> Created json file: {file} <<")
            
            with open(self._dict[file],mode='r',encoding='utf8') as jfile:
                setattr(self, file,json.load(jfile))

        self.channel_dict = {}
        self.dynamic_voice_list = []


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
        with open(f'{self._db_location}/cache.json','w',encoding="utf-8") as jfile:
            self.cache[key] = value
            json.dump(self.cache,jfile,indent=4,ensure_ascii=False)

    def get_channel_dict(self,channel_type:str=None):
        return self.channel_dict.get(channel_type) if channel_type else self.channel_dict
    
    def set_channel_dict(self,key,data):
        self.channel_dict[key] = data

    def getif_dynamic_voice(self,channel_id):
        return channel_id if channel_id in self.dynamic_voice_list else None
    
    def update_dynamic_voice(self,new_channel_id=None,remove_channel_id=None):
        if new_channel_id:
            self.dynamic_voice_list.append(new_channel_id)
        if remove_channel_id:
            self.dynamic_voice_list.remove(remove_channel_id)

    def set_dynamic_voice(self,data:list):
        self.dynamic_voice_list = data
        

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
    if TYPE_CHECKING:
        lol_champion: pd.DataFrame

    def __init__(self):
        self._db_location = "./database"
        self._filepath = {
            'lol_champion': f'{self._db_location}/lol_champion.csv'
        }

        if not os.path.isdir(self._db_location):
            os.mkdir(self._db_location)
        
        for file in self._filepath:
            if os.path.isfile(self._filepath[file]):
                setattr(self, file,pd.read_csv(open(self._filepath[file],mode='r',encoding='utf8')))
            else:
                print(f"Missing file: {self._filepath[file]}")

    def read_data_to_list(self,path):
        with open(f'{path}.csv', 'r') as csvfile:
            csvReader = csv.reader(csvfile)
            data = list(csvReader)
        for row in data:
            print(row)
        return data
    
    def read_data_to_dict_reader(self,path):
        with open(f'{path}.csv', 'r') as csvfile:
            csvReader = csv.DictReader(csvfile)
        for row in csvReader:
                print(row)
        return csvReader
    
    def write_data(self,path,data:list):
        with open(f'{path}.csv', 'r', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(data)

    def write_data_with_dict_writer(self,path,field:list,data:dict):
        with open(f'{path}.csv', 'r', newline='') as csvfile:
            dictWriter = csv.DictWriter(csvfile, fieldnames = field)
            dictWriter.writeheader()
            dictWriter.writerow(data)
    
    @staticmethod
    def find_row_by_column_value(file_path, column_name, target_value):
        df = pd.read_csv(file_path)
        row = df[df[column_name] == target_value]
        if not row.empty:
            return row.iloc[0]  # Return the first matching row
        return None
    
    def get_row_by_column_value(self,df:pd.DataFrame,colume,value) -> pd.Series:
        """給予指定欄位與其值，尋找符合的資料
        :param df: 要尋找的資料表
        :param colume: 尋找資料的條件欄位
        :param value: 尋找資料的條件值
        """
        row = df[df[colume] == value]
        if not row.empty:
            return row.iloc[0]
        return pd.Series()


class XmlDatabase:
    pass