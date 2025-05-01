import json
import logging
import os
from typing import TYPE_CHECKING, TypeVar

T = TypeVar("T")
logger = logging.getLogger("star")

class BaseJsonHandler:
    _DBPATH = "./database"

    if TYPE_CHECKING:
        datas: dict[str, T]

    def __init__(self, filename:str):
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

    def get(self, key:str, default:T=None) -> T:
        try:
            data = self.datas[key]
        except KeyError:
            data = default
            self.write(key, default)
        finally:
            return data
    
    def write(self, key:str, value):
        self.datas[key] = value
        with open(f'{self._DBPATH}/{self.filename}.json', 'w', encoding='utf-8') as jfile:
            json.dump(self.datas, jfile, indent=4)

    def update_dict(self, key:str, value:dict):
        """Update a dictionary in the JSON file with a new key-value pair."""
        if key not in self.datas:
            self.datas[key] = {}
        self.datas[key].update(value)
        self.write(key, self.datas[key])

    def __getitem__(self, key):
        return self.get(key)

class JsonConfig(BaseJsonHandler):
    def __init__(self):
        super().__init__("setting")

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
        tokens: JsonToken

    __slots__ = [
        "lol_jdict",
        "jdict",
        "picdata",
        "tokens",
        "options",
        "config",
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
        self.config = JsonConfig()
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
        Writes the given data to the specified file in the JSON.

        Args:
            file_name (str): The name of the file to write the data to.
            data (dict): The data to be written to the file.

        Raises:
            KeyError: If the specified file_name is not found in the JSON.
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