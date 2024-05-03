import asyncio
import json
import secrets
import time
from datetime import datetime
from enum import Enum, IntEnum

import discord
import feedparser
import google.generativeai as genai
import pandas as pd
import requests
import spotify_dl
import yt_dlp
from bs4 import BeautifulSoup
from faker import Faker
#from pydantic import BaseModel

from starcord import log,Jsondb
from starcord.DataExtractor import TwitchAPI, YoutubeAPI, YoutubeRSS, CWA_API
from starcord.starAI import StarGeminiAI

# db = CsvDatabase()
# r = db.get_row_by_column_value(db.lol_champion,"name_tw","凱莎")
# print(r.loc["name_en"])

if __name__ == '__main__':
	pass
	starai = StarGeminiAI()
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
			# "XX12：我想配個6000多的電腦 大概要多少錢？",
			# "拔辣：如果使用電擊（不會威脅生命），電擊28、34腦區，是否能引起內嗅皮質的活躍性？",
			# "拔辣：請問顳葉「內側」28與34腦區分別功能是？",
			# "拔辣：星羽，妳喜歡下棋嗎",
			# "拔辣：在64格棋盤上，只有2個白色主教，1個黑色騎士。其中一個白色主教位於E5，另一個白色主教位於C8，黑色騎士位於D4，請問黑白哪方會贏？",
			# "威立：剛剛的問題可不可以再複述一次？使用條列的方式分析黑色方與白色方",
   			"請以妳自己的性格創造一個故事中的角色，但名子中不要有星這個字",
	  		# "星羽 妳知道無黨籍這個政黨嗎",
	 		# "威立：星羽 如果你是台中摃殘黨的主席，同時又當選總統，那你會如何對待選輸的海豹，執行共殘黨理念中的「把不要的總統放進消波塊流放邊疆」？",
			# "星羽 請將快樂營政黨的以SWOT分析後作成表格",
			"如果你有一個專屬武器，那會叫什麼？是什麼樣的武器？",
			 ]
	# for i in content:
	# 	print(f"{i}：")
	# 	print(starai.generate_aitext(f"{i}"))
	# 	print("="*50)
	# 	time.sleep(10)

# 	url = "https://youtu.be/UcEHstSuAiM?si=b1Qs3GWXpCTZP_4g"
# 	info = yt_dlp.YoutubeDL({
#     # "format": "bestaudio/best",
#     "outtmpl": "%(extractor)s-%(id)s-%(title)s.%(ext)s",
#     "restrictfilenames": True,
#     "noplaylist": False,
#     "nocheckcertificate": True,
#     "ignoreerrors": False,
#     "logtostderr": False,
#     "quiet": True,
#     "no_warnings": True,
#     "default_search": "auto",
#     "source_address": "0.0.0.0",
#     'extractor_retries': 3,
# }).extract_info(url, download=False)
# 	print(info)
# 	with open("music.json","w") as f:
# 		json.dump(info, f)

	# CWA_API().get_weather_warning()

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