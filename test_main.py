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
#from pydantic import BaseModel

from starcord import log,Jsondb
from starcord.DataExtractor import TwitchAPI, YoutubeAPI, YoutubeRSS
from starcord.starAI import generate_aitext

# db = CsvDatabase()
# r = db.get_row_by_column_value(db.lol_champion,"name_tw","凱莎")
# print(r.loc["name_en"])

if __name__ == '__main__':
	pass
	for _ in range(5):
		content =".星羽 你認為台中摃殘黨與山珍海味黨有何異同"
		print(generate_aitext(f"威立：{content[1:]}"))
		time.sleep(3)
	# CHANNEL_ID = "UCbh7KHPMgYGgpISdbF6l0Kw"
	# youtube_feed = f'https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}'
	# feed = feedparser.parse(youtube_feed)
	# for entry in feed['entries']:
	# 	print(entry)
	# api = YoutubeAPI()
	# id = api.get_channel_id("sakagawa_0309")
	# print(id)
	
	# from cmds.task import slice_list
	# list = YoutubeRSS().get_videos("UCNkJevYXQcjTc70j45FXFjA")
	# list.reverse()
	# print(len(list))
	# for i in list:
	# 	print(i.updated_at)
	# time = datetime.fromisoformat("2024-02-18 06:52:51+08:00")
	# print(len(slice_list(list,time)))

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

	# from cmds.task import slice_list
	# ytchannels = ["UCNkJevYXQcjTc70j45FXFjA"]
	# cache_youtube = "2024-02-15T04:07:49+08:00"
	# rss = YoutubeRSS()
	# log.info("youtube_video start")
	# for ytchannel_id in ytchannels:
	# 	#抓取資料
	# 	rss_data = rss.get_videos(ytchannel_id)
	# 	#log.info(rss_data)
	# 	if not rss_data:
	# 		continue
	# 	cache_last_update_time = datetime.fromisoformat(cache_youtube)
	# 	log.info(cache_last_update_time)
	# 	#判斷是否有更新
	# 	log.info(rss_data[0].updated_at)
	# 	log.info(f"{rss_data[0].updated_at > cache_last_update_time}")
	# 	if not cache_last_update_time or rss_data[0].updated_at > cache_last_update_time:
			
	# 		#整理影片列表&儲存最後更新時間
	# 		rss_data.reverse()
	# 		video_list = slice_list(rss_data, cache_last_update_time)
	# 		log.info(video_list)
	# 		#發布通知
	# 		for video in video_list:
	# 			log.info(f"{video.title}:{video.updated_at}")
	# 			log.info(f"sec: {ytchannel_id}")