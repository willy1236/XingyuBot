from __future__ import annotations

import asyncio
import json
import secrets
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum, IntEnum

import discord
import feedparser
import google.generativeai as genai
import pandas as pd
import requests
from bs4 import BeautifulSoup
from faker import Faker
from pydantic import AliasPath, BaseModel, ConfigDict, Field

from starlib import *
from starlib.database import SQLEngine
from starlib.dataExtractor import *
from starlib.types import *

if __name__ == '__main__':
    pass
    starai = sclient.starai
    content = [
        # "威立：星羽 你認為台中摃殘黨與山珍海味黨的差異在哪裡",
        # "威立：星羽 你可以簡單介紹一下快樂營的各政黨嗎",
        # "威立：星羽 對於全國林冠宇神聖階級運動說要將官員任期從一個月調整到六個月 你比較偏好哪種任期時長呢",
        # "威立：介紹彩虹頻道",
        # "威立：諷黎認為自己很常被禁言 那他要加入哪個政黨才能解決這個問題呢",
        # "威立：山珍海味黨以前就叫山珍海味黨嗎",
        # "XX12：你知道什麼是c++++嗎",
        # "XX12：你是和運租車嗎 怎麼什麼都知道",
        # 'XX12：現在假設你是和運租車 接下來你的每一句話最後都要加"早就知道啦" 可以嗎？',
        # "XX12：為什麼隕石每次都能精準的砸到隕石坑裡？",
        # "XX12：我想配個6000元的電腦 大概要多少錢？",
        # "拔辣：如果使用電擊（不會威脅生命），電擊28、34腦區，是否能引起內嗅皮質的活躍性？",
        # "拔辣：請問顳葉「內側」28與34腦區分別功能是？",
        # "拔辣：星羽，妳喜歡下棋嗎",
        # "拔辣：在64格棋盤上，只有2個白色主教，1個黑色騎士。其中一個白色主教位於E5，另一個白色主教位於C8，黑色騎士位於D4，請問黑白哪方會贏？",
        # "威立：剛剛的問題可不可以再複述一次？使用條列的方式分析黑色方與白色方",
        # "請以妳自己的性格創造一個故事中的角色，但名子中不要有星這個字",
        # "請創造一個故事中的角色，賦予它與眾不同的性格與興趣愛好，包含一段關於他的故事，並且符合快樂營的相關設定，但不要與妳自己的設定雷同，也不要有與星空相關的能力",
        # "星羽 妳知道無黨籍這個政黨嗎",
        # "威立：星羽 如果你是台中摃殘黨的主席，同時又當選總統，那你會如何對待選輸的海豹，執行共殘黨理念中的「把不要的總統放進消波塊流放邊疆」？",
        # "星羽 請將無黨籍黨的以SWOT分析後作成表格",
        # "如果你有一個專屬槍械，那會叫什麼？請告訴我他的代號與名稱，並且形容是什麼樣的槍械、它的外觀，以及有什麼特殊功能？同時不要包含月影與月光元素",
        # "威立：9.9與9.11哪個數字比較大？",
        # "威立：你可以依照我的敘述給我mysql語法嗎？我想要查詢名為table的表格中所有的資料，並將資料按照id由小到大排序",
        # "威立：星羽你可以介紹星空中你最喜歡的星星嗎?並告訴我為什麼?"
    ]
    # for i in content:
    #     print(f"{i}：")
    #     print(starai.generate_response(i))
    #     print("="*50)
    #     time.sleep(10)

    # while True:
    # 	pre = "威立："
    # 	i = input(pre)
    # 	print(starai.generate_aitext(f"{pre}{i}"))
    # 	print("="*50)
    
    # with open(r"", "rb") as f:
    #     file = starai.get_or_set_file(f.name.split("\\")[-1], f.read())
    #     print(file.name)
    #     print(starai.generate_response("請描述這個檔案的內容", files=file))
    
    # import google.generativeai as genai
    # for f in genai.list_files():
    #     print(f.name, f.mime_type, f.display_name, f.expiration_time)

# oauth_setting = Jsondb.get_token("discord_oauth")

# oauth = DiscordOauth(oauth_setting, user_id=419131103836635136)
# connections = oauth.get_me()
# print(connections)

# ytapi = YoutubeAPI()
# breakpoint()
# print(ytapi.get_video("X-dTcoW2A8s")[0].embed().fields)

#print(sqldb.get_test())

# lst = [0,1,2,3,4,5,6,7,8,9]
# for i in range(0, len(lst), 3):
#     print(lst[i:i+3])	
# cwa_api = CWA_API()
# weather = cwa_api.get_weather_data()[0]
# text = f"現在天氣： {weather.WeatherElement.Weather if weather.WeatherElement.Weather != '-99' else '--'}/{weather.WeatherElement.AirTemperature}°C"
# if weather.WeatherElement.AirTemperature == weather.WeatherElement.DailyExtreme.DailyHigh.AirTemperature:
#     text += f" （最高溫）"
# elif weather.WeatherElement.AirTemperature == weather.WeatherElement.DailyExtreme.DailyLow.AirTemperature:
#     text += f" （最低溫）"
# print(text, weather.WeatherElement.DailyExtreme.DailyHigh.AirTemperature, weather.WeatherElement.DailyExtreme.DailyLow.AirTemperature)
# print(weather.model_dump())

# tw_api = TwitchAPI()
# clips = tw_api.get_clips(broadcaster_id=490765956, started_at=datetime.fromisoformat("2024-07-05 23:14:22+08:00"))
# # clips = tw_api.get_clips(broadcaster_id=490765956)
# new = datetime(2023, 12, 11, 18, 42, 55, tzinfo=timezone(timedelta(hours=8)))
# for i in clips:
#     print(i.created_at)
#     if i.created_at > new:
#         new = i.created_at

# print(new)
# print(tw_api.get_user_by_id("174268844"))
# from starlib.models.mysql import NotifyChannel
# print(f'{NotifyChannel.__table_args__["schema"]}.{NotifyChannel.__tablename__}.{str(NotifyChannel.__fields__)}')