import requests,genshin,asyncio,discord,secrets,starcord
from bs4 import BeautifulSoup
import pandas as pd

from starcord.DataExtractor.community import TwitchAPI
#from pydantic import BaseModel

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


if __name__ == '__main__':
	pass

	import feedparser
	CHANNEL_ID = "UCLRkp9Xg_-cjQ0RuVZ0VZnA"
	youtube_feed = f'https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}'
	feed = feedparser.parse(youtube_feed)
	for entry in feed['entries']:
		print(entry)

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