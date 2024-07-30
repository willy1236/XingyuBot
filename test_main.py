from __future__ import annotations

import asyncio
import json
import secrets
import time
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum, IntEnum

import discord
import feedparser
import genshin
import google.generativeai as genai
import pandas as pd
import requests
from bs4 import BeautifulSoup
from faker import Faker
from pydantic import BaseModel, Field, ConfigDict, AliasPath

from starlib import ChoiceList, Jsondb, log, sqldb, tz
from starlib.dataExtractor import *
from starlib.starAI import StarGeminiAI
from starlib.types import NotifyCommunityType

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
# 			"""
# 沉默寡言的信差。
# 按照本人的說法，並不是將想法藏在心中，而只是單純的沒有什麼想法。
# 雖然給人喜歡獨處的感覺，不過事實上大多時候還是和企鵝物流其他成員一起出現。
# 德克薩斯小姐雖然平常沉默寡言，但她的戰鬥風格卻意外地，可以用暴風驟雨來形容。
# 雖然羅德島中，沒有接受過正統訓練的幹員反而佔多數，但其中大部分在使用武器時，仍然會具有某種共通的章法，而德克薩斯小姐完全不具備這種章法。
# 雖然她現在已經相當收斂，但從一些她自己都未必注意到的習慣中仍然可以發現，她所掌握的戰鬥方式是非常直白的，與任何武器無關的，一切只為消滅對方這個目的服務的，殺人術。
# 無論是魯珀族的身份，還是顯眼的毛色，以及戰鬥方式，當然，還有名字本身，都將德克薩斯小姐的身份指向已覆滅的德克薩斯家族。那個家族曾經盛極一時，而如今，連名字都已被多數人遺忘。
# 若真是如此，那德克薩斯小姐的過去，或許比一般人所能想像的極限還要瘋狂許多，德克薩斯家族這個名字本身，可以為此擔保。
# 不過，一方面，即使是羅德島的情報網，也對那個家族的情況知之甚少，另一方面，德克薩斯小姐似乎也沒有提及自己過去的意圖，那麼至少此時此刻，並沒有去深挖的必要，畢竟，或許如她所說，總有一天，她的過去會追上她。
# 唯一可以肯定的一點是，雖然德克薩斯小姐從不提及自己的過去，但與其說避而不談，更傾向於無所謂。
# 可以看得出她確實十分適應如今的生活，而不是想要在其中逃避什麼，平淡的工作，吵鬧的同伴，龍門，羅德島，這就是現在的她的一切。
# 或許可以這麼斷言：
# 即使過去找上門來，德克薩斯小姐依然會從容以對，但若是她的過去擾亂了她的現在，那，或許我們能夠見到，她真正憤怒的樣子。

# 德克薩斯這傢伙可麻煩了，就算是承認了一個人，也不會跟那個人多說幾句，我當時都花了點時間才確定是不是算跟她搞好關係了。
# 唉，誰要是要當她的朋友，我看可要遭罪嘍~
# ——能天使

# 你如何理解德克薩斯小姐的性格？
# 			"""
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
			"威立：星羽你可以介紹星空中你最喜歡的星星嗎?並告訴我為什麼?"
			 ]
	for i in content:
		print(f"{i}：")
		print(starai.generate_aitext(f"{i}"))
		print("="*50)
		time.sleep(10)
	 
	while True:
		pre = "威立："
		i = input(pre)
		print(starai.generate_aitext(f"{pre}{i}"))
		print("="*50)

# class Test(BaseModel):
# 	name: str
# 	time: datetime

# dct = {"name": "test", "time": "2024-07-05T23:14:21Z"}
# obj = Test(**dct)
# print(obj.name)
# print(obj.time)
# obj = Test.model_validate(dct)
# #obj = Test(dct)
# print(obj.name)

# from typing import TypedDict

class classrole(IntEnum):
	role1 = 1
	role2 = 2
	role3 = 3

# class lUser(TypedDict):
# 	id: int
# 	username: str
# 	discriminator: str
# 	global_name: str | None
# 	avatar: str | None
# 	role: classrole
    
# dict = {"id": 123, "role": 1}
# luser = lUser(dict)
# print(type(luser))
# print(type(luser["role"]))

# @dataclass(slots=True)
# class kUser():
# 	id: int
# 	role: classrole
# 	time: datetime

# 	def __post_init__(self):
# 		self.time = datetime.fromisoformat(self.time)

# data = {"id":1, "role": 1, "time": "2024-07-05T23:14:21+08:00"}
# user = kUser(**data)
# print(user)
# print(type(user))
# print(user.time, type(user.time))
# print(type(user.role), user.role == classrole.role1)

# api = TwitchAPI()
# user = sqldb.get_dcuser_v2("419131103836635136")
# print(user)
# dict = {
# 	"id": 1,
# 	"role": 1,
# 	"time": {
# 		"created_at": "2024-07-05T23:14:21+08:00"
# 	}
# 	#"time.created_at": "2024-07-05T23:14:21+08:00"
# }

# class jUser(BaseModel):
# 	id: int
# 	role: int
# 	created_at: datetime = Field(validation_alias=AliasPath('time', 'created_at'))

# user = jUser(**dict)
# print(user, sys.getsizeof(user))