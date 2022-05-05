import discord,json,requests
from discord.ext import commands
from bs4 import BeautifulSoup

from core.classes import Cog_Extension
from library import find,BRS
from BotLib.basic import Database

def player_search(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")
    results = soup.find_all("h1",class_="row")

    for result in results:
        if result.div.string == None:
            result2 = str(result.div)[166:]
            lvl = ''.join([x for x in result2 if x.isdigit()])
            return lvl

API_URL = 'https://osu.ppy.sh/api/v2'
TOKEN_URL = 'https://osu.ppy.sh/oauth/token'
def get_osutoken():
    data = {
        'client_id': Database().osu_API_id,
        'client_secret': Database().osu_API_secret,
        'grant_type': 'client_credentials',
        'scope': 'public'
    }
    response = requests.post(TOKEN_URL, data=data)
    return response.json().get('access_token')

    
def get_osuplayer(user):
    token = get_osutoken()
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }
    response = requests.get(f'{API_URL}/users/{user}', headers=headers)
    return response.json()

def get_apexplayer(user):
    headers = {
        'TRN-Api-Key': Database().TRN_API,
        'Accept': 'application/json',
        'Accept-Encoding': 'gzip'
    }
    response = requests.get(f'https://public-api.tracker.gg/v2/apex/standard/profile/origin/{user}', headers=headers)
    return response.json().get('data')



class OsuPlayer():
    def __init__(self,data):
        self.username = data['username']
        self.id = data['id']
        self.global_rank = data['statistics']['global_rank']
        self.pp = data['statistics']['pp']
        self.avatar_url = data['avatar_url']
        self.country = data['country']["code"]
        self.is_online = data['is_online']

class ApexPlayer():
    def __init__(self,data):
        self.username = data['platformInfo']['platformUserId']
        self.platformSlug = data['platformInfo']['platformSlug']

class game(Cog_Extension):
    gdata = Database().gdata
    games = ['steam','osu','apex','lol']

    @commands.command()
    async def lol(self,ctx,*arg):
        if arg[0] == 'player':
            player = arg[1]
            url = 'https://lol.moa.tw/summoner/show/'+player
            lvl = player_search(url) or '讀取失敗'

            embed = discord.Embed(title="LOL玩家查詢", url=url, color=0xc4e9ff)
            embed.add_field(name="玩家名稱", value=player, inline=False)
            embed.add_field(name="等級", value=lvl, inline=False)
            embed.add_field(name="查詢戰績", value="LOL戰績網(lol.moa.tw)", inline=False)
            embed.set_thumbnail(url='https://i.imgur.com/B0TMreW.png')
        
            await ctx.send(embed=embed)
        else:
            await ctx.send('目前沒有這種用法喔')

    @commands.group(invoke_without_command=True)
    async def game(self,ctx):
        pass
        
    @game.command()
    async def set(self,ctx,game,data=None):
        if not str(ctx.author.id) in self.gdata:
            self.gdata[f'{ctx.author.id}'] = {}
            Database().write('gdata',self.gdata)
            await ctx.send('偵測到資料庫內無使用者資料，已自動註冊',delete_after=5)

        if game in self.games:
            user = str(ctx.author.id)

            if not game in self.gdata[user]:
                self.gdata[user][game] = 'None'
                #await ctx.send('偵測到資料庫內無使用者資料，已自動補齊')

            if data == None:
                self.gdata[user][game] = 'None'
                await ctx.send(f'已重設{game}資料')
            else:
                self.gdata[user][game] = data
                await ctx.send(f'已將{game}資料設定為 {data}')
            Database().write('gdata',self.gdata)
        
        else:
            await ctx.send(f'遊戲錯誤:此遊戲目前未開放設定\n目前支援:{self.games}',delete_after=10)

    @game.command()
    @commands.is_owner()
    async def find(self,ctx,user):
        user = await find.user(ctx,user)
        if user != None:
            data = {}
            for game in self.games:
                if game in self.gdata[f'{user.id}']:
                    data[game] = self.gdata[f'{user.id}'][game]
                else:
                    data[game] = 'None'

            embed = BRS.simple(title=user)
            for game in self.games:
                embed.add_field(name=game, value=data[game], inline=False)
            embed.set_thumbnail(url=user.display_avatar.url)
            await ctx.send(embed=embed)

    @commands.command()
    @commands.cooldown(rate=1,per=5)
    async def osu(self,ctx,userid):
        msg = await ctx.send('資料查詢中...')
        async with ctx.typing():
            user = OsuPlayer(get_osuplayer(userid))
            embed = BRS.simple("Osu玩家資訊")
            embed.add_field(name="名稱",value=user.username)
            embed.add_field(name="id",value=user.id)
            embed.add_field(name="全球排名",value=user.global_rank)
            embed.add_field(name="pp",value=user.pp)
            embed.add_field(name="國家",value=user.country)
            embed.add_field(name="是否在線上",value=user.is_online)
            embed.set_thumbnail(url=user.avatar_url)
            await ctx.send(embed=embed)
        await msg.edit(content='查詢成功',embed=embed)

    @commands.command()
    @commands.cooldown(rate=1,per=5)
    async def apex(self,ctx,userid):
        msg = await ctx.send('資料查詢中...')
        user = ApexPlayer(get_apexplayer(userid))
        embed = BRS.simple("Apex玩家資訊")
        embed.add_field(name="名稱",value=user.username)
        embed.add_field(name="平台",value=user.platformSlug)
        await msg.edit(content='查詢成功',embed=embed)

def setup(bot):
    bot.add_cog(game(bot))