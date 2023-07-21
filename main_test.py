import requests,genshin,asyncio,discord
import starcord
from starcord.type.game import DatabaseGame
from enum import Enum
from starcord.type.user import PetType
from starcord.clients import NotionAPI

# text = 'osu'
# print(text in dir(DatabaseGame))
#print(PetType('cat'))

# class SpeakingState(Enum):
#     """Speaking state"""

#     none = 0
#     voice = 1
#     soundshare = 2
#     priority = 4

#     def __str__(self):
#         return self.name

#     def __int__(self):
#         return self.value
    
# print(str(SpeakingState.voice))

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

NotionAPI().search("")