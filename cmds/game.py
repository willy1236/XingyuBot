import discord,requests
from discord.ext import commands
from bs4 import BeautifulSoup

from core.classes import Cog_Extension
from library import find,BRS
from BotLib.basic import Database
from BotLib.gamedata import *

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
        raise commands.errors.ArgumentParsingError('game command')
        
    @game.command()
    async def set(self,ctx,game,data=None):
        if not str(ctx.author.id) in self.gdata:
            self.gdata[f'{ctx.author.id}'] = {}
            Database().write('gdata',self.gdata)
            await ctx.send('偵測到資料庫內無使用者資料，已自動註冊',delete_after=5)

        if game in self.games:
            user = str(ctx.author.id)

            if not game in self.gdata[user]:
                self.gdata[user][game] = None
                #await ctx.send('偵測到資料庫內無使用者資料，已自動補齊')

            if data == None:
                self.gdata[user][game] = None
                await ctx.send(f'已重設{game}資料')
            else:
                self.gdata[user][game] = data
                await ctx.send(f'已將{game}資料設定為 {data}')
            Database().write('gdata',self.gdata)
        
        else:
            await ctx.send(f'遊戲錯誤:此遊戲目前未開放設定\n目前支援:{self.games}',delete_after=10)

    @game.command()
    async def find(self,ctx,user=None):
        if user == None:
            user = ctx.author
        else:
            user = await find.user(ctx,user)
        if user == ctx.author or ctx.author.id == 419131103836635136:
            if user != None and str(user.id) in self.gdata:
                data = {}
                for game in self.games:
                    if game in self.gdata[str(user.id)]:
                        data[game] = self.gdata[str(user.id)][game]
                    else:
                        data[game] = 'None'

                embed = BRS.simple(title=user)
                for game in self.games:
                    embed.add_field(name=game, value=data[game], inline=False)
                embed.set_thumbnail(url=user.display_avatar.url)
                await ctx.send(embed=embed)
            else:
                await ctx.send('無法查詢此人的資料，可能是無此用戶或用戶尚未註冊資料庫',delete_after=5)
        else:
            await ctx.send('目前不開放查詢別人的資料喔',delete_after=5)

    @commands.group(invoke_without_command=True)
    @commands.cooldown(rate=1,per=1)
    async def osu(self,ctx,userid=None):
        msg = await ctx.send('資料查詢中...')
        #資料庫調用
        if not userid:
            userid = Database().gdata[str(ctx.author.id)]['osu']
        else:
            dcuser = await find.user2(ctx,userid)
            if dcuser:
                userid = Database().gdata[str(dcuser.id)]['osu']
        
        embed = OsuData().get_player(userid).desplay
        if embed:
            await msg.edit(content='查詢成功',embed=embed)
        else:
            await msg.edit(content='查詢失敗:查無此ID',delete_after=5)

    @osu.command()
    @commands.cooldown(rate=1,per=1)
    async def map(self,ctx,mapid):
        msg = await ctx.send('資料查詢中...')
        embed = OsuData().get_beatmap(mapid).desplay
        if embed:
            await msg.edit(content='查詢成功',embed=embed)
        else:
            await msg.edit(content='查詢失敗:查無此ID',delete_after=5)

    @commands.group(invoke_without_command=True)
    @commands.cooldown(rate=1,per=3)
    async def apex(self,ctx,userid=None):
        msg = await ctx.send('資料查詢中...')
        #資料庫調用
        if not userid:
            userid = Database().gdata[str(ctx.author.id)]['apex']
        else:
            dcuser = await find.user2(ctx,userid)
            if dcuser:
                userid = Database().gdata[str(dcuser.id)]['apex']
        
        embed = ApexData().get_player(userid).desplay
        if embed:
            await msg.edit(content='查詢成功',embed=embed)
        else:
            await msg.edit(content='查詢失敗:查無此ID',delete_after=5)

    @apex.command()
    @commands.cooldown(rate=1,per=3)
    async def map(self,ctx):
        msg = await ctx.send('資料查詢中...')
        embed = ApexData.get_map_rotation().desplay
        await msg.edit(content='查詢成功',embed=embed)

    @apex.command()
    @commands.cooldown(rate=1,per=3)
    async def crafting(self,ctx):
        msg = await ctx.send('資料查詢中...')
        embed = ApexData.get_crafting().desplay
        await msg.edit(content='查詢成功',embed=embed)

    @apex.command(enabled=False)
    @commands.cooldown(rate=1,per=3)
    async def server(self,ctx):
        msg = await ctx.send('資料查詢中...')
        embed = ApexData.get_status().desplay
        await msg.edit(content='查詢成功',embed=embed)

    @commands.group(invoke_without_command=True)
    @commands.cooldown(rate=1,per=1)
    async def DBD(self,ctx,userid=None):
        msg = await ctx.send('資料查詢中...')
        #資料庫調用
        if not userid:
            userid = Database().gdata[str(ctx.author.id)]['dbd']
        else:
            dcuser = await find.user2(ctx,userid)
            if dcuser:
                userid = Database().gdata[str(dcuser.id)]['dbd']
        
        embed = DBDData().get_player(userid).desplay
        if embed:
            await msg.edit(content='查詢成功',embed=embed)
        else:
            await msg.edit(content='查詢失敗:查無此ID',delete_after=5)

def setup(bot):
    bot.add_cog(game(bot))