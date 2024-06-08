import json
import os
from typing import TYPE_CHECKING

defaule_json = {
    "jdata": {
        "task_report": 0,
        "feedback_channel": 0,
        "error_report": 0,
        "report_channel": 0,
        "dm_channel": 0,
        "mentioned_channel": 0,
        "mention_everyone_channel": 0,
        "happycamp_guild": [ 0 ],
        "main_guilds": [ 0 ],
        "debug_guilds": [ 0 ],
        "SQLsettings" : {
            "host": "",
            "port": "",
            "user": "",
            "password": "",
            "db": ""
        },
        "bot_code": "Bot1",
        "activity": "",
        "debug_mode": True,
        "log_level": "DEBUG",
        "voice_updata": True,
        "api_website": False,
        "auto_update": False,
        "SQL_connection": False,
        "file_log": False,
        "Mongedb_connection": False,
        "twitch_bot": False
    }
}

class JsonDatabase():
    if TYPE_CHECKING:
        lol_jdict: dict
        jdict: dict
        jdata: dict
        picdata: dict
        cache: dict
        tokens: dict
        options: dict
        channel_dict: dict
        dynamic_voice_list: list

    __slots__ = [
        "_DBPATH",
        "_PATH_DICT",
        "lol_jdict",
        "jdict",
        "jdata",
        "picdata",
        "cache",
        "tokens",
        "options",
    ]

    def __init__(self,create_file=True):
        """
        CWB = 中央氣象局

        TRN = tracker.gg
        """
        self._DBPATH = "./database"
        self._PATH_DICT = {
            'lol_jdict': f'{self._DBPATH}/lol_dict.json',
            'jdict': f'{self._DBPATH}/dict.json',
            'jdata': f'{self._DBPATH}/setting.json',
            #'cdata': f'{self.location}/channel_settings.json',
            'picdata': f'{self._DBPATH}/picture.json',
            'options': f'{self._DBPATH}/command_option.json',
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
        # craete folder
        if not os.path.isdir(self._DBPATH):
            os.mkdir(self._DBPATH)
            print(f">> Created folder: {self._DBPATH} <<")
        
        for file in self._PATH_DICT:
            path = self._PATH_DICT[file]
            if not os.path.isfile(path):
                if not create_file:
                    continue
                with open(path,'w',encoding='utf-8') as jfile:
                    json.dump(defaule_json.get(file,{}),jfile,indent=4)
                    print(f">> Created json file: {file} <<")
            
            with open(path,mode='r',encoding='utf8') as jfile:
                setattr(self, file, json.load(jfile))


    def write(self, file_name: str, data: dict):
        """
        Writes the given data to the specified file in the database.

        Args:
            file_name (str): The name of the file to write the data to.
            data (dict): The data to be written to the file.

        Raises:
            KeyError: If the specified file_name is not found in the database.
        """
        try:
            location = self._PATH_DICT[file_name]
            setattr(self, file_name, data)
            with open(file=location, mode='w', encoding='utf8') as jfile:
                json.dump(data, jfile, indent=4, ensure_ascii=False)
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
            
    def set_token(self, name:str, value:str|dict):
        self.tokens[name] = value
        self.write('tokens',self.tokens)
        
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
        return self.jdict[key].get(value,value)