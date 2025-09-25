from __future__ import annotations

import asyncio
import difflib
import json
import secrets
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum, IntEnum

import discord
import feedparser
import pandas as pd
import requests
from pydantic import AliasPath, BaseModel, ConfigDict, Field

from starlib import *
from starlib.database import SQLEngine
from starlib.dataExtractor import *
from starlib.types import *

if __name__ == "__main__":
    pass

# cwa_api = CWA_API()
# weather = cwa_api.get_weather_data()[0]
# text = f"現在天氣： {weather.WeatherElement.Weather if weather.WeatherElement.Weather != '-99' else '--'}/{weather.WeatherElement.AirTemperature}°C"
# if weather.WeatherElement.AirTemperature == weather.WeatherElement.DailyExtreme.DailyHigh.AirTemperature:
#     text += f" （最高溫）"
# elif weather.WeatherElement.AirTemperature == weather.WeatherElement.DailyExtreme.DailyLow.AirTemperature:
#     text += f" （最低溫）"
# print(text, weather.WeatherElement.DailyExtreme.DailyHigh.AirTemperature, weather.WeatherElement.DailyExtreme.DailyLow.AirTemperature)
# print(weather.model_dump())


# import nmap

# # 建立掃描器
# nm = nmap.PortScanner()

# # 掃描整個區段，-sn 表示只做 ping 掃描
# scan_range = ""
# nm.scan(hosts=scan_range, arguments="-sn")

# # 輸出存活主機
# print(f"掃描區段 {scan_range} 結果：")
# for host in nm.all_hosts():
#     # print(
#     #     f"主機：{host} ({nm[host].hostname()})"
#     #     f"，狀態：{nm[host].state()}"
#     #     f"，開放端口：{nm[host].all_tcp() if nm[host].all_tcp() else '無'}"
#     #     f"，協議：{nm[host].all_protocols() if nm[host].all_protocols() else '無'}"
#     #     f"，操作系統：{nm[host]['osmatch'][0]['name'] if 'osmatch' in nm[host] else '未知'}"
#     #     f"，MAC 地址：{nm[host]['addresses'].get('mac', '無')}"
#     #     f"，製造商：{nm[host]['vendor'].get(nm[host]['addresses'].get('mac', ''), '無')}"
#     #     f"，掃描時間：{nm[host].uptime() if 'uptime' in nm[host] else '未知'}"
#     #     f"，主機名稱: {nm[host].hostname()}"
#     # )

#     print(f"完整資料：{nm[host]}")
