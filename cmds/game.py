import discord
from discord.ext import commands
import json,requests
from bs4 import BeautifulSoup
from core.classes import Cog_Extension
from library import find

jdata = json.load(open('setting.json',mode='r',encoding='utf8'))

with open('database/gamer_data.json',mode='r',encoding='utf8') as jfile:
    gdata = json.load(jfile)

games = ['steam','osu','apex','lol']

def player_search(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")
    results = soup.find_all("h1",class_="row")

    for result in results:
        if result.div.string == None:
            result2 = str(result.div)[166:]
            lvl = ''.join([x for x in result2 if x.isdigit()])
            return lvl

class game(Cog_Extension):
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
        if not str(ctx.author.id) in gdata:
            with open('database/gamer_data.json',mode='r+',encoding='utf8') as jfile:
                gdata[f'{ctx.author.id}'] = {}
                json.dump(gdata,jfile,indent=4)
            await ctx.send('偵測到資料庫內無使用者資料，已自動註冊',delete_after=5)

        if game in games:
            user = str(ctx.author.id)

            if not game in gdata[user]:
                with open('database/gamer_data.json',mode='r+',encoding='utf8') as jfile:
                    gdata[user][game] = 'None'
                    json.dump(gdata,jfile,indent=4)
                #await ctx.send('偵測到資料庫內無使用者資料，已自動補齊')

            with open('database/gamer_data.json',mode='r+',encoding='utf8') as jfile:
                if data == None:
                    gdata[user][game] = 'None'
                    await ctx.send(f'已重設{game}資料')
                else:
                    gdata[user][game] = data
                    await ctx.send(f'已將{game}資料設定為 {data}')
                json.dump(gdata,jfile,indent=4)
        
        else:
            await ctx.send(f'遊戲錯誤:此遊戲目前未開放設定\n目前支援:{games}',delete_after=10)

    @game.command()
    @commands.is_owner()
    async def find(self,ctx,user):
        user = await find.user(ctx,user)
        if user != None:
            data = {}
            for game in games:
                if game in gdata[f'{user.id}']:
                    data[game] = gdata[f'{user.id}'][game]
                else:
                    data[game] = 'None'

            embed = discord.Embed(title=user, color=0xc4e9ff)
            for game in games:
                embed.add_field(name=game, value=data[game], inline=False)
            embed.set_thumbnail(url=user.display_avatar.url)
            await ctx.send(embed=embed)



def setup(bot):
    bot.add_cog(game(bot))