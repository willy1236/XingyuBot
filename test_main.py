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
   			# "請以妳自己的性格創造一個故事中的角色，但名子中不要有星這個字",
	  			"星羽 妳知道無黨籍這個政黨嗎",
			 ]
	# for i in content:
	# 	print(f"{i}：")
	# 	print(starai.generate_aitext(f"{i}"))
	# 	print("="*50)
	# 	time.sleep(10)

	# url = "https://www.bilibili.com/video/BV15C4y1Z7bL/?spm_id_from=333.788.recommend_more_video.0&vd_source=99697669d29e9e85eb52b2b6e795b986"
	# info = yt_dlp.YoutubeDL().extract_info(url, download=False)
	# print(info)
	# with open("music.json","w") as f:
	# 	json.dump(info, f)
	import subprocess

	# 設定 Spotify 播放清單的連結
	spotify_playlist_link = "https://open.spotify.com/playlist/0EuV0NfZDbhUIl9hIltB0E"

	# 執行 spotify_dl
	subprocess.run(["spotify_dl", "-l", spotify_playlist_link])

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