import requests,genshin,asyncio,discord,secrets
from enum import Enum
#from pydantic import BaseModel
from starcord.clients import RiotClient
from starcord.database.file import CsvDatabase

# class MyClass:
#     def __init__(self, data_dict):
#         for key, value in data_dict.items():
#             setattr(self, key, value)

# class MyClass:
#     __slots__ = ['name', 'age', 'city']

#     def __init__(self, data_dict):
#         for key, value in data_dict.items():
#             if key in self.__slots__:
#                 setattr(self, key, value)

# # 創建一個字典
# data = {"name": "John", "age": 25, "city": "New York", "country": "USA"}

# # 創建一個類的實例並將字典內容設置為屬性
# obj = MyClass(data)

# # 訪問類的屬性
# print(obj.name)  # 輸出：John
# print(obj.age)   # 輸出：25
# print(obj.city)  # 輸出：New York
# print(obj.country)  # 這行會引發AttributeError
#NotionAPI().search("")

#data = {"test": "1"}
# JsonStorageAPI().append_data(data=data)

r = RiotClient().get_summoner_masteries("")
print(r)
# db = CsvDatabase()
# r = db.get_row_by_column_value(db.lol_champion,"name_tw","凱莎")
# print(r.loc["name_en"])