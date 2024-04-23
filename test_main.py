import asyncio
import secrets
import time
from datetime import datetime
from enum import Enum, IntEnum

import discord
import feedparser
import requests
import pandas as pd
from bs4 import BeautifulSoup
from faker import Faker
import google.generativeai as genai
#from pydantic import BaseModel

from starcord import log,Jsondb
from starcord.DataExtractor import TwitchAPI, YoutubeAPI, YoutubeRSS
from starcord.starAI import generate_aitext

# db = CsvDatabase()
# r = db.get_row_by_column_value(db.lol_champion,"name_tw","凱莎")
# print(r.loc["name_en"])

if __name__ == '__main__':
	pass

	content = [
			"威立：星羽 你認為台中摃殘黨與山珍海味黨的差異在哪裡",
			"威立：星羽 你可以簡單介紹一下快樂營的各政黨嗎",
			"威立：星羽 對於全國林冠宇神聖階級運動說要將官員任期從一個月調整到六個月 你比較偏好哪種任期時長呢",
			"威立：介紹彩虹頻道",
			"威立：諷黎認為自己很常被禁言 那他要加入哪個政黨才能解決這個問題呢",
			"威立：山珍海味黨以前就叫山珍海味黨嗎",
			 ]
	for i in content:
		print(f"{i}：")
		print(generate_aitext(f"{i}"))
		print("="*50)
		time.sleep(10)

	#df = RiotAPI().get_rank_dataframe("SakaGawa#0309")
	# df = pd.read_csv('my_data.csv').sort_values("tier")
	# #counts = df['tier'].value_counts()
	# #print(str(counts))
	# dict = {
	# 	"RANKED_FLEX_SR": "彈性積分",
	# 	"RANKED_SOLO_5x5": "單/雙"
	# }
	# for idx,data in df.iterrows():
	# 	print(data["name"],dict.get(data["queueType"]),data["tier"] + " " + data["rank"])
	#df.to_csv('my_data.csv', index=False)