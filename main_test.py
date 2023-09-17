import requests,genshin,asyncio,discord,secrets,time,datetime
from enum import Enum
#from pydantic import BaseModel
from starcord.clients import RiotClient,StarClient
from starcord.types import DBGame
from starcord.database.file import CsvDatabase

# class MyClass:
#     def __init__(self, data_dict):
#         for key, value in data_dict.items():
#             setattr(self, key, value)

# class MyClass:
#     __slots__ = ['name', 'age', 'city']

#data = {"test": "1"}
# JsonStorageAPI().append_data(data=data)
# db = CsvDatabase()

# rclient = RiotClient()
# player = rclient.get_player_byname("")
# match_list = rclient.get_player_matchs(player.puuid,3)
# kda_avg = 0
# i = 0
# for match_id in match_list:
#     match = rclient.get_match(match_id)
#     print(match.gameMode)
#     if match.gameMode != "CLASSIC":
#         continue
    
#     i += 1
#     player_im = match.get_player_in_match(player.name)
    
#     championName = db.get_row_by_column_value(db.lol_champion,"name_en",player_im.championName)
#     print(f"第{i}場：{championName.loc['name_tw']} {player_im.lane} KDA {player_im.kda}")
#     kda_avg += player_im.kda
#     time.sleep(1)

# kda_avg = round(kda_avg / 5, 2)

# print(f"Avg. {kda_avg}")

# db = CsvDatabase()
# r = db.get_row_by_column_value(db.lol_champion,"name_tw","凱莎")
# print(r.loc["name_en"])