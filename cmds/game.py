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



def setup(bot):
    bot.add_cog(game(bot))