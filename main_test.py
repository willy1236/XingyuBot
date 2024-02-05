import requests,genshin,asyncio,discord,secrets,starcord
from bs4 import BeautifulSoup
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

import asyncio,aiohttp,webbrowser,requests,json,os
from aiohttp import web
from aiohttp.web_runner import GracefulExit

class DiscordAPI:
	def __init__(self):
		self.API_ENDPOINT = 'https://discord.com/api/v10'
		self.TOKEN_ENDPOINT = "https://discord.com/api/oauth2/token"
		self.AUTH_URL = "https://discord.com/api/oauth2/authorize?client_id=870923985569861652&redirect_uri=http%3A%2F%2Flocalhost%3A500%2Fcallback&response_type=code&scope=identify"
		self.CLIENT_ID = ''
		self.CLIENT_SECRET = ''
		self.REDIRECT_URI = 'http://localhost:500/callback'
		self.access_token = None
		self.refresh_token = None

	def set_auth_token(self):
		if not os.path.exists('oauth_tokens.json'):
			loop = asyncio.get_event_loop()
			app = loop.run_until_complete(self.authenticate(loop))
			web.run_app(app, port=500, print=False,loop=loop)

		with open("oauth_tokens.json", "r") as oauth_tokens:
				jtoken = json.load(oauth_tokens)
				#可依實際狀況更改此處
				self.access_token = jtoken.get('access_token')
				self.refresh_token = jtoken.get('refresh_token')

	async def authenticate(self,loop):
		async def callback(request):
			code = request.query['code']

			token_url_params = {
				'grant_type': 'authorization_code',
				'code': code,
				'redirect_uri': self.REDIRECT_URI
			}

			try:
				async with request.app['session'].post(self.TOKEN_ENDPOINT, data=token_url_params,timeout=aiohttp.ClientTimeout(total=10), auth=aiohttp.BasicAuth(self.CLIENT_ID, self.CLIENT_SECRET)) as response:
					data = await response.json()
					with open("oauth_tokens.json", "w") as oauth_tokens:
						json.dump(data, oauth_tokens)
					#signal.alarm(3)
				return web.Response(text=f"授權成功！\n{token_url_params}")
			except asyncio.TimeoutError:
				return web.Response(text="請求超時，請重試。")
			
		async def shutdown(request):
			#print("will shutdown now")
			raise GracefulExit()

		webbrowser.open(self.AUTH_URL)

		app = web.Application()
		app.router.add_get('/callback', callback)
		app.router.add_get('/shutdown', shutdown)
		app['session'] = aiohttp.ClientSession(loop=loop)
		app['loop'] = loop
		
		# 設定在指定時間後自動關閉
		# asyncio.create_task(self._close_app())
		
		return app

	# async def _close_app(self):
	# 	# 在指定時間後，停止事件循環
	# 	await asyncio.sleep(120)
	# 	async with requests.get("http://localhost:500/shutdown") as response:
	# 		pass


	def exchange_code(self,code):
		data = {
			'grant_type': 'authorization_code',
			'code': code,
			'redirect_uri': self.REDIRECT_URI
		}
		headers = {
			'Content-Type': 'application/x-www-form-urlencoded'
		}
		r = requests.post('%s/oauth2/token' % self.API_ENDPOINT, data=data, headers=headers, auth=(self.CLIENT_ID, self.CLIENT_SECRET))
		r.raise_for_status()
		return r.json()

	def refresh_access_token(self,refresh_token):
		data = {
			'grant_type': 'refresh_token',
			'refresh_token': refresh_token
		}
		headers = {
			'Content-Type': 'application/x-www-form-urlencoded'
		}
		r = requests.post('%s/oauth2/token' % self.API_ENDPOINT, data=data, headers=headers, auth=(self.CLIENT_ID, self.CLIENT_SECRET))
		r.raise_for_status()
		return r.json()

	def revoke_access_token(self,access_token):
		data = {
			'token': access_token,
			'token_type_hint': 'access_token'
		}
		headers = {
			'Content-Type': 'application/x-www-form-urlencoded'
		}
		requests.post('%s/oauth2/token/revoke' % self.API_ENDPOINT, data=data, headers=headers, auth=(self.CLIENT_ID, self.CLIENT_SECRET))

	def get_me(self):
		headers = {
			'Authorization': f'Bearer {self.access_token}'
		}
		r = requests.get('%s/users/@me' % self.API_ENDPOINT, headers=headers)
		return r.json()

if __name__ == '__main__':
	# dc = DiscordAPI()
	# dc.set_auth_token()

	# print(dc.access_token)

	# import feedparser
	# CHANNEL_ID = "UCNkJevYXQcjTc70j45FXFjA"
	# youtube_feed = f'https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}'
	# feed = feedparser.parse(youtube_feed)
	# for entry in feed['entries']:
	# 	print(entry['media_thumbnail'][0]["url"])

	def slice_list(lst:list[dict], target_id, radius=0):
		index = next((i for i, d in enumerate(lst) if d["id"] == target_id), None)
		if index is None:
			return lst
		
		#start_index = max(0, index - radius)
		#end_index = min(len(lst), index + radius + 1)
		#return lst[start_index:end_index]

		return lst[index:]

	# 示例列表
	my_list = [
		{"id": 1, "value": 10},
		{"id": 2, "value": 20},
		{"id": 3, "value": 30},
		{"id": 4, "value": 40},
		{"id": 5, "value": 50},
		{"id": 6, "value": 60},
		{"id": 7, "value": 70},
		{"id": 8, "value": 80},
		{"id": 9, "value": 90},
		{"id": 10, "value": 100}
	]
	target_id = None
	radius = 0
	result = slice_list(my_list, target_id, radius)
	print(result)
