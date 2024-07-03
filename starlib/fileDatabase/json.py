import json
import os
from typing import TYPE_CHECKING


class BaseJsonHandler:
    _DBPATH = "./database"

    def __init__(self, filename):
        self.filename = filename

        # craete folder
        if not os.path.isdir(self._DBPATH):
            os.mkdir(self._DBPATH)
            print(f">> Created folder: {self._DBPATH} <<")
        
        path = f'{self._DBPATH}/{filename}.json'
        if not os.path.isfile(path):
            with open(path, 'w', encoding='utf-8') as jfile:
                json.dump({}, jfile, indent=4)
                print(f">> Created json file: {filename} <<")
        
        with open(path, 'r', encoding='utf8') as jfile:
            self.datas = json.load(jfile)

    def get(self, key, default=None):
        try:
            data = self.datas[key]
        except KeyError:
            data = default
            self.write(key, default)
        finally:
            return data
    
    def write(self, key, value):
        self.datas[key] = value
        with open(f'{self._DBPATH}/{self.filename}.json', 'w', encoding='utf-8') as jfile:
            json.dump(self.datas, jfile, indent=4)

class JsonConfig(BaseJsonHandler):
    def __init__(self):
        super().__init__("setting")

class JsonCache(BaseJsonHandler):
    def __init__(self):
        super().__init__("cache")

    def add_dict_data(self, key, target, value):
        """Add a key-value pair to a dictionary stored in the cache.\\
        usually used in notify_community data in the cache.
        """
        dict_data:dict = self.get(key)
        dict_data[target] = value
        self.write(key, dict_data)

    def remove_dict_data(self, key, target):
        """Remove a key-value pair from a dictionary stored in the cache.\\
        usually used in notify_community data in the cache.
        """
        dict_data:dict = self.get(key)
        if target in dict_data:
            del dict_data[target]
            self.write(key, dict_data)
            return True
        return False

class JsonDatabase():
    if TYPE_CHECKING:
        lol_jdict: dict
        jdict: dict
        picdata: dict
        tokens: dict
        options: dict

        config: JsonConfig
        cache: JsonCache

    __slots__ = [
        "lol_jdict",
        "jdict",
        "picdata",
        "tokens",
        "options",
        "config",
        "cache",
    ]

    _DBPATH = "./database"
    _PATH_DICT = {
        'lol_jdict': f'{_DBPATH}/lol_dict.json',
        'jdict': f'{_DBPATH}/dict.json',
        'picdata': f'{_DBPATH}/picture.json',
        'options': f'{_DBPATH}/command_option.json',
        'tokens': f'{_DBPATH}/token.json'
    }

    def __init__(self,create_file=True):
        """
        CWB = 中央氣象局

        TRN = tracker.gg
        """
        self.config = JsonConfig()
        self.cache = JsonCache()

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
                    json.dump({}, jfile, indent=4)
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

    def get_jdict(self,key,value):
        """取得jdict資料"""
        return self.jdict[key].get(value,value)