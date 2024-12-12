import json
import logging
import os
from typing import TYPE_CHECKING, TypeVar

from ..types.datatype import JsonCacheType

T = TypeVar("T")
logger = logging.getLogger("star")

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

    def get(self, key, default=None) -> dict | list | str | None:
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

    def __getitem__(self, key):
        return self.get(key)

class JsonConfig(BaseJsonHandler):
    def __init__(self):
        super().__init__("setting")

class JsonCache(BaseJsonHandler):
    def __init__(self):
        super().__init__("cache")

class JsonToken(BaseJsonHandler):
    def __init__(self):
        super().__init__("token")

class JsonDatabase():
    if TYPE_CHECKING:
        lol_jdict: dict
        jdict: dict
        picdata: dict
        options: dict
        member_names: dict

        config: JsonConfig
        cache: JsonCache
        tokens: JsonToken

    __slots__ = [
        "lol_jdict",
        "jdict",
        "picdata",
        "tokens",
        "options",
        "config",
        "cache",
        "member_names",
    ]

    _DBPATH = "./database"
    _PATH_DICT = {
        'lol_jdict': f'{_DBPATH}/lol_dict.json',
        'jdict': f'{_DBPATH}/dict.json',
        'picdata': f'{_DBPATH}/picture.json',
        'options': f'{_DBPATH}/command_option.json',
        'tokens': f'{_DBPATH}/token.json',
        "member_names": f'{_DBPATH}/member_names.json'
    }

    def __init__(self,create_file=True):
        """
        CWB = 中央氣象局

        TRN = tracker.gg
        """
        self.config = JsonConfig()
        self.cache = JsonCache()
        self.tokens = JsonToken()

        # craete folder
        if not os.path.isdir(self._DBPATH):
            os.mkdir(self._DBPATH)
            logger.info(f">> Created folder: {self._DBPATH} <<")
        
        for file in self._PATH_DICT:
            path = self._PATH_DICT[file]
            if not os.path.isfile(path):
                if not create_file:
                    continue
                with open(path,'w',encoding='utf-8') as jfile:
                    json.dump({}, jfile, indent=4)
                    logger.info(f">> Created json file: {file} <<")
            
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
        """
        token = self.tokens[webname]
        if token:
            return token
        else:
            raise ValueError('無此API token')
            
    def get_picture(self, id) -> str:
        """取得圖片網址"""
        return self.picdata[id]
            
    def set_token(self, name:str, value:str | dict):
        self.tokens[name] = value
        self.write('tokens',self.tokens)

    def get_jdict(self,key:str, value:str) -> str:
        """取得jdict資料"""
        return self.jdict[key].get(value,value)
    
    def set_cache(self, key: str | JsonCacheType, target: str, value):
        """Add a key-value(target-value) pair to a dictionary stored in the cache.\\
        usually used in notify_community data in the cache.
        """
        if isinstance(key, JsonCacheType):
            key = key.value
        dict_data = self.cache.get(key)
        dict_data[target] = value
        logger.debug(f"set_cache: {key} {target}: {value}")
        self.cache.write(key, dict_data)

    def remove_cache(self, key: str | JsonCacheType, target: str):
        """Remove a key-value(target-value) pair from a dictionary stored in the cache.\\
        usually used in notify_community data in the cache.
        """
        if isinstance(key, JsonCacheType):
            key = key.value
        dict_data = self.cache.get(key)
        try:
            del dict_data[target]
            self.cache.write(key, dict_data)
            logger.debug(f"remove_cache: {key}/{target}")
            return True
        except KeyError:
            return False
    
    def get_cache(self, key: str | JsonCacheType) -> dict | str | None:
        """
        Retrieve a full data from the cache using the provided key.
        """
        if isinstance(key, JsonCacheType):
            key = key.value
        return self.cache.get(key)
    
    def write_cache(self, key: str | JsonCacheType, value: dict | str):
        """
        Writes a full data to the cache.
        """
        if isinstance(key, JsonCacheType):
            key = key.value
        self.cache.write(key, value)

    def get_tw(self, value:T, option_name:str) -> str | T:
        """
        Retrieve the Traditional Chinese (zh-TW) translation for a given value and option name.
        Args:
            value (T): The value to be translated.
            option_name (str): The name of the option to look up in the dictionary.
        Returns:
            str | T: The translated value if found, otherwise the original value.
        """
        if self.jdict.get(option_name):
            if self.jdict[option_name].get("zh-TW"):
                return self.jdict[option_name]["zh-TW"].get(str(value),value)
            else:
                return self.jdict[option_name].get(str(value),value)
            
        elif self.options.get(option_name):
            return self.options[option_name][str(value)]["zh-TW"]
        
        else:
            return value
        
    def get_member_name(self, id:int) -> str | None:
        """取得成員名稱"""
        return self.member_names.get(str(id))